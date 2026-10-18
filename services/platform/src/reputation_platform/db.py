"""PostgreSQL persistence for immutable reports and leased evaluation jobs."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from reputation_core.admission import CandidateRecord
from reputation_core.application import AgentDetail, AgentSummary, EvaluationJob, ReportSummary, normalize_reference
from reputation_core.reporting import EvaluationReport
from reputation_core.scoring import ScoringOutcome
from reputation_platform.settings import PROJECT_ROOT


class LeaseLostError(RuntimeError):
    pass


class EvidenceIntegrityError(ValueError):
    pass


@dataclass
class _ImportedReport:
    directory: Path
    manifest_hash: str
    report_hash: str
    report: EvaluationReport
    registration_reference: str
    evidence_files: dict[str, str]
    candidates: list[tuple[CandidateRecord, Path, str]]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validated_report(value: dict) -> EvaluationReport:
    payload = dict(value)
    supplied_scores = payload.pop("scores", None)
    report = EvaluationReport.model_validate_json(json.dumps(payload, ensure_ascii=False))
    if supplied_scores != report.scores.model_dump(mode="json"):
        raise EvidenceIntegrityError("Report scores do not match the evidence-derived calculation")
    return report


class Repository:
    def __init__(self, dsn: str, root: Path = PROJECT_ROOT) -> None:
        self._dsn = dsn
        self.root = root.resolve()
        self.runtime = self.root / "runtime"

    def _connect(self):
        return psycopg.connect(self._dsn, row_factory=dict_row)

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))

    def health(self) -> bool:
        with self._connect() as connection:
            return connection.execute("SELECT 1 AS ready").fetchone()["ready"] == 1

    def _runtime_file(self, value: str | Path) -> Path:
        path = (self.root / value).resolve()
        parts = {part.lower() for part in path.parts}
        if (not path.is_relative_to(self.runtime) or not path.is_file()
            or parts & {"platform-config", "secrets", ".git", ".venv", ".codex"}
            or any(part.startswith(".") or ".private" in part.lower() for part in path.parts)
            or re.search(r"(?:secret|password|api[-_]?key)", path.name, re.IGNORECASE)):
            raise EvidenceIntegrityError("Only retained public runtime evidence may be imported or downloaded")
        return path

    def _manifest(self, directory: Path) -> tuple[dict, dict[str, str]]:
        manifest_path = self._runtime_file(directory / "manifest.json")
        manifest = json.loads(manifest_path.read_bytes())
        references = list(manifest["inputs"])
        if manifest.get("schema_version") == "admission-input-manifest-v1":
            references = [{"path": item[f"{kind}_file"], "sha256": item[f"{kind}_sha256"]}
                          for item in references for kind in ("observation", "response")
                          if item.get(f"{kind}_file")]
        if manifest.get("implementation_note"):
            references.append(manifest["implementation_note"])
        hashes = {}
        for reference in references:
            expected = reference["sha256"]
            if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
                raise EvidenceIntegrityError("Invalid input digest in report manifest")
            path = (self.root / reference["path"]).resolve()
            if path.is_relative_to(self.runtime):
                path = self._runtime_file(path)
            elif not (path.is_relative_to(self.root / "docs/adr") or path.is_relative_to(self.root / "configs")):
                raise EvidenceIntegrityError("Manifest input is outside retained evidence and public policy configuration")
            if not path.is_file() or _sha(path) != expected:
                raise EvidenceIntegrityError("A retained report input changed or is missing")
            hashes[path.relative_to(self.root).as_posix()] = expected
        return manifest, hashes

    def _candidates(self, path: Path) -> list[CandidateRecord]:
        payload = json.loads(path.read_bytes())
        if payload.get("schema_version") != "candidate-admission-v1":
            raise EvidenceIntegrityError("Unsupported candidate snapshot schema")
        candidates = []
        for item in payload["candidates"]:
            candidate = dict(item)
            candidate.pop("ready_for_full_score", None)
            candidates.append(CandidateRecord.model_validate(candidate))
        keys = [candidate.key for candidate in candidates]
        if len(set(keys)) != len(keys):
            raise EvidenceIntegrityError("Candidate snapshot contains duplicate identities")
        return candidates

    def _load_report(self, supplied: str | Path) -> _ImportedReport:
        path = (self.root / supplied).resolve()
        directory = path if path.is_dir() else path.parent
        if not directory.is_relative_to(self.runtime) or (path.is_file() and path.name != "report.json"):
            raise EvidenceIntegrityError("Import requires a retained runtime report directory or report.json")
        _, hashes = self._manifest(directory)
        report_path = self._runtime_file(directory / "report.json")
        report = _validated_report(json.loads(report_path.read_bytes()))
        policies = [json.loads((self.root / name).read_bytes()) for name in hashes
                    if Path(name).parent == Path("configs/pilots") and Path(name).suffix == ".json"]
        policies = [policy for policy in policies if policy.get("policy_version") == report.scores.policy_version]
        if len(policies) != 1:
            raise EvidenceIntegrityError("A report requires one verified pilot configuration for its scoring policy")
        policy = policies[0]
        registration_reference = normalize_reference(
            f"eip155:{policy['chain_id']}:{policy['registry']}:{policy['agent_id']}"
        )
        if registration_reference is None:
            raise EvidenceIntegrityError("The verified pilot configuration has no valid full registration identity")
        references = set(report.source_references)
        references.update(value for explanation in report.samples for value in explanation.sample.evidence)
        permitted = {}
        for reference in references:
            normalized = reference.replace("\\", "/")
            if not normalized.startswith("runtime/"):
                continue
            if any(part in ("", ".", "..") for part in normalized.split("/")):
                raise EvidenceIntegrityError("A report evidence path is not canonical")
            evidence = self._runtime_file(normalized)
            name = evidence.relative_to(self.root).as_posix()
            if name not in hashes or _sha(evidence) != hashes[name]:
                raise EvidenceIntegrityError("A referenced evidence file is absent from the verified input manifest")
            permitted[name] = hashes[name]
        candidates = []
        for name, source_hash in hashes.items():
            if Path(name).name != "admission-report.json":
                continue
            source = self._runtime_file(name)
            candidates.extend((candidate, source.parent, source_hash)
                              for candidate in self._candidates(source) if candidate.key == report.candidate_key)
        return _ImportedReport(directory, _sha(directory / "manifest.json"), _sha(report_path), report,
                               registration_reference, permitted, candidates)

    def _upsert_agent(self, connection, *, key: str, name: str, reference: str, description: str = "") -> None:
        canonical = normalize_reference(reference)
        row = connection.execute("""INSERT INTO agents(key,name,registration_reference,description)
            VALUES (%s,%s,%s,%s) ON CONFLICT(key) DO UPDATE SET
            name=EXCLUDED.name,registration_reference=CASE WHEN %s THEN EXCLUDED.registration_reference
                ELSE agents.registration_reference END,
            description=CASE WHEN EXCLUDED.description='' THEN agents.description ELSE EXCLUDED.description END,
            updated_at=clock_timestamp()
            WHERE NOT (%s AND agents.registration_reference ~ '^eip155:[0-9]+:0x[0-9a-f]{40}:[0-9]+$'
                AND agents.registration_reference <> EXCLUDED.registration_reference)
            RETURNING key""", (key, name, canonical or reference, description, canonical is not None,
                               canonical is not None)).fetchone()
        if row is None:
            raise EvidenceIntegrityError("An internal agent key cannot be rebound to a different registered identity")

    def _insert_candidate(self, connection, candidate: CandidateRecord, directory: Path, source_hash: str) -> None:
        self._upsert_agent(connection, key=candidate.key, name=candidate.name, reference=candidate.registration_reference)
        connection.execute("""INSERT INTO candidate_metadata(id,agent_key,source_directory,source_sha256,validated_json)
            VALUES (%s,%s,%s,%s,%s) ON CONFLICT(agent_key,source_sha256) DO NOTHING""",
            (uuid4(), candidate.key, directory.relative_to(self.root).as_posix(), source_hash,
             Jsonb(candidate.model_dump(mode="json"))))

    @staticmethod
    def _summary(row: dict) -> ReportSummary:
        payload = row["validated_json"]
        return ReportSummary(id=str(row["id"]), candidate_key=row["agent_key"], generated_at=row["generated_at"],
                             scope=payload["scope"], scores=ScoringOutcome.model_validate(payload["scores"]))

    def _insert_report(self, connection, imported: _ImportedReport) -> ReportSummary:
        report = imported.report
        self._upsert_agent(connection, key=report.candidate_key, name=report.name,
                           reference=imported.registration_reference, description=report.scope)
        for candidate, directory, source_hash in imported.candidates:
            self._insert_candidate(connection, candidate, directory, source_hash)
        row = connection.execute("""INSERT INTO reports(id,agent_key,generated_at,source_directory,
            manifest_sha256,report_sha256,validated_json,evidence_files) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(report_sha256) DO NOTHING RETURNING *""",
            (uuid4(), report.candidate_key, report.generated_at, imported.directory.relative_to(self.root).as_posix(),
             imported.manifest_hash, imported.report_hash, Jsonb(report.model_dump(mode="json")),
             Jsonb(imported.evidence_files))).fetchone()
        if row is None:
            row = connection.execute("SELECT * FROM reports WHERE report_sha256=%s", (imported.report_hash,)).fetchone()
        return self._summary(row)

    def import_report(self, path: str | Path) -> ReportSummary:
        imported = self._load_report(path)
        with self._connect() as connection:
            return self._insert_report(connection, imported)

    def import_candidates(self, path: str | Path) -> int:
        source = (self.root / path).resolve()
        source = self._runtime_file(source / "admission-report.json" if source.is_dir() else source)
        self._manifest(source.parent)
        candidates = self._candidates(source)
        source_hash = _sha(source)
        with self._connect() as connection:
            for candidate in candidates:
                self._insert_candidate(connection, candidate, source.parent, source_hash)
        return len(candidates)

    def list_reports(self, agent_key: str) -> list[ReportSummary]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM reports WHERE agent_key=%s ORDER BY generated_at DESC,imported_at DESC,id",
                                      (agent_key,)).fetchall()
        return [self._summary(row) for row in rows]

    def list_agents(self) -> list[AgentSummary]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM agents ORDER BY lower(name),key").fetchall()
            reports = connection.execute("SELECT * FROM reports ORDER BY generated_at DESC,imported_at DESC,id").fetchall()
        grouped = {}
        for row in reports:
            grouped.setdefault(row["agent_key"], []).append(self._summary(row))
        return [AgentSummary(key=row["key"], name=row["name"], registration_reference=row["registration_reference"],
            description=row["description"], report_count=len(grouped.get(row["key"], [])),
            latest_report=grouped[row["key"]][0] if grouped.get(row["key"]) else None) for row in rows]

    def get_agent(self, key: str) -> AgentDetail | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM agents WHERE key=%s", (key,)).fetchone()
            if row is None:
                return None
            reports = connection.execute("SELECT * FROM reports WHERE agent_key=%s ORDER BY generated_at DESC,imported_at DESC,id",
                                         (key,)).fetchall()
            candidate = connection.execute("SELECT validated_json FROM candidate_metadata WHERE agent_key=%s ORDER BY imported_at DESC,id LIMIT 1",
                                           (key,)).fetchone()
        summaries = [self._summary(item) for item in reports]
        return AgentDetail(agent=AgentSummary(key=key, name=row["name"], registration_reference=row["registration_reference"],
            description=row["description"], report_count=len(summaries), latest_report=summaries[0] if summaries else None),
            reports=summaries, candidate=CandidateRecord.model_validate(candidate["validated_json"]) if candidate else None)

    def get_report(self, report_id: str) -> EvaluationReport | None:
        with self._connect() as connection:
            row = connection.execute("SELECT validated_json FROM reports WHERE id=%s", (UUID(str(report_id)),)).fetchone()
        return _validated_report(row["validated_json"]) if row else None

    def evidence_file(self, report_id: str, path: str) -> Path | None:
        with self._connect() as connection:
            row = connection.execute("SELECT evidence_files FROM reports WHERE id=%s", (UUID(str(report_id)),)).fetchone()
        normalized = path.replace("\\", "/")
        if row is None or normalized not in row["evidence_files"]:
            return None
        resolved = self._runtime_file(normalized)
        if _sha(resolved) != row["evidence_files"][normalized]:
            raise EvidenceIntegrityError("Published evidence changed after import")
        return resolved

    @staticmethod
    def _job(row: dict) -> EvaluationJob:
        return EvaluationJob(id=str(row["id"]), reference=row["reference"], status=row["status"], stage=row["stage"],
            message=row["message"], candidate_key=row["candidate_key"], report_id=str(row["report_id"]) if row["report_id"] else None,
            created_at=row["created_at"], updated_at=row["updated_at"])

    @staticmethod
    def _lease(row: dict) -> dict:
        result = dict(row)
        result["id"] = str(result["id"])
        if result["report_id"] is not None:
            result["report_id"] = str(result["report_id"])
        return result

    def create_job(self, reference: str) -> EvaluationJob:
        value = reference.strip()
        if not value:
            raise ValueError("Registration reference must not be blank")
        canonical = normalize_reference(value) or value
        with self._connect() as connection:
            row = connection.execute("""INSERT INTO evaluation_jobs(id,reference) VALUES (%s,%s)
                ON CONFLICT(reference) WHERE status IN ('QUEUED','RUNNING') DO UPDATE SET reference=EXCLUDED.reference
                RETURNING *""", (uuid4(), canonical)).fetchone()
        return self._job(row)

    def get_job(self, job_id: str) -> EvaluationJob | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM evaluation_jobs WHERE id=%s", (UUID(str(job_id)),)).fetchone()
        return self._job(row) if row else None

    @staticmethod
    def _lease_seconds(value: int) -> int:
        if type(value) is not int or value <= 0:
            raise ValueError("Lease duration must be a positive integer")
        return value

    def claim_job(self, worker: str, lease_seconds: int = 60) -> dict | None:
        if not worker.strip():
            raise ValueError("Worker identity must not be blank")
        with self._connect() as connection:
            row = connection.execute("""WITH next_job AS (
                SELECT id FROM evaluation_jobs WHERE status='QUEUED'
                    OR (status='RUNNING' AND lease_until<=clock_timestamp())
                ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1
            ) UPDATE evaluation_jobs AS job SET status='RUNNING',stage='COLLECTING',
                message='平台正在采集资料并选择评价方案。',lease_owner=%s,
                lease_until=clock_timestamp()+(%s * interval '1 second'),
                fencing_token=job.fencing_token+1,report_id=NULL,updated_at=clock_timestamp()
              FROM next_job WHERE job.id=next_job.id RETURNING job.*""",
              (worker, self._lease_seconds(lease_seconds))).fetchone()
        return self._lease(row) if row else None

    def renew_job(self, job_id: str, worker: str, fence: int, lease_seconds: int = 60) -> dict:
        with self._connect() as connection:
            row = connection.execute("""UPDATE evaluation_jobs SET lease_until=clock_timestamp()+(%s * interval '1 second'),
                updated_at=clock_timestamp() WHERE id=%s AND status='RUNNING' AND lease_owner=%s
                AND fencing_token=%s AND lease_until>clock_timestamp() RETURNING *""",
                (self._lease_seconds(lease_seconds), UUID(str(job_id)), worker, fence)).fetchone()
            if row is None:
                raise LeaseLostError("Evaluation lease is no longer owned by this worker")
        return self._lease(row)

    def set_job_stage(self, job_id: str, worker: str, fence: int, stage: str, message: str,
                      candidate_key: str | None = None) -> EvaluationJob:
        if stage not in {"COLLECTING", "VERIFYING", "REPORTING"}:
            raise ValueError("A running job requires an active execution stage")
        with self._connect() as connection:
            row = connection.execute("""UPDATE evaluation_jobs SET stage=%s,message=%s,
                candidate_key=COALESCE(%s,candidate_key),updated_at=clock_timestamp()
                WHERE id=%s AND status='RUNNING' AND lease_owner=%s AND fencing_token=%s
                AND lease_until>clock_timestamp() RETURNING *""",
                (stage, message, candidate_key, UUID(str(job_id)), worker, fence)).fetchone()
            if row is None:
                raise LeaseLostError("Evaluation lease is no longer owned by this worker")
        return self._job(row)

    def finalize_job(self, job_id: str, worker: str, fence: int, *, status: str, message: str,
                     candidate_key: str | None = None, report_directory: str | Path | None = None) -> EvaluationJob:
        if status not in {"COMPLETE", "NEEDS_INFO", "UNSUPPORTED", "FAILED"}:
            raise ValueError("Finalization requires a terminal job status")
        imported = self._load_report(report_directory) if status == "COMPLETE" and report_directory is not None else None
        if status == "COMPLETE" and imported is None:
            raise ValueError("Completion requires a newly generated, validated report")
        if status != "COMPLETE" and report_directory is not None:
            raise ValueError("A report is only published when its job completes")
        with self._connect() as connection:
            current = connection.execute("""SELECT * FROM evaluation_jobs WHERE id=%s AND status='RUNNING'
                AND lease_owner=%s AND fencing_token=%s AND lease_until>clock_timestamp() FOR UPDATE""",
                (UUID(str(job_id)), worker, fence)).fetchone()
            if current is None:
                raise LeaseLostError("Evaluation lease is no longer owned by this worker")
            if current["candidate_key"] and candidate_key and current["candidate_key"] != candidate_key:
                raise ValueError("Final candidate does not match the job's bound candidate")
            bound_candidate = candidate_key or current["candidate_key"]
            report_id = None
            if imported is not None:
                if bound_candidate is None or imported.report.candidate_key != bound_candidate:
                    raise ValueError("Report candidate does not match the job's bound candidate")
                if imported.registration_reference != normalize_reference(current["reference"]):
                    raise ValueError("Report registration identity does not match the submitted job")
                if imported.report.generated_at <= current["created_at"]:
                    raise ValueError("A previous report cannot substitute for a newly executed evaluation")
                summary = self._insert_report(connection, imported)
                report_id = UUID(summary.id)
            row = connection.execute("""UPDATE evaluation_jobs SET status=%s,stage='DONE',message=%s,
                candidate_key=%s,report_id=%s,lease_owner=NULL,lease_until=NULL,updated_at=clock_timestamp()
                WHERE id=%s AND status='RUNNING' AND lease_owner=%s AND fencing_token=%s
                AND lease_until>clock_timestamp() RETURNING *""",
                (status, message, bound_candidate, report_id, UUID(str(job_id)), worker, fence)).fetchone()
            if row is None:
                raise LeaseLostError("Evaluation lease expired before finalization")
        return self._job(row)
