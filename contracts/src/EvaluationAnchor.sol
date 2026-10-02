// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @notice Local report commitments. Separate admin and evaluator permissions.
contract EvaluationAnchor {
    error Unauthorized();
    error ZeroField();
    error PreviousHashMismatch();
    error ConflictingReport();

    struct Head {
        bytes32 reportHash;
        uint64 sequence;
    }

    struct Record {
        bool exists;
        bytes32 policyHash;
        bytes32 previousReportHash;
        uint64 sequence;
    }

    address public immutable admin;
    mapping(address => bool) public isEvaluator;
    mapping(address => mapping(bytes32 => Head)) private heads;
    mapping(address => mapping(bytes32 => mapping(bytes32 => Record))) private records;

    event EvaluatorPermissionChanged(address indexed evaluator, bool allowed);
    event ReportAnchored(
        address indexed evaluator,
        bytes32 indexed agentKey,
        bytes32 indexed reportHash,
        bytes32 policyHash,
        bytes32 previousReportHash,
        uint64 sequence
    );

    constructor() {
        admin = msg.sender;
    }

    function setEvaluator(address evaluator, bool allowed) external {
        if (msg.sender != admin) revert Unauthorized();
        if (evaluator == address(0)) revert ZeroField();
        isEvaluator[evaluator] = allowed;
        emit EvaluatorPermissionChanged(evaluator, allowed);
    }

    function anchorReport(bytes32 agentKey, bytes32 reportHash, bytes32 policyHash, bytes32 previousReportHash)
        external
        returns (uint64 sequence)
    {
        if (!isEvaluator[msg.sender]) revert Unauthorized();
        if (agentKey == bytes32(0) || reportHash == bytes32(0) || policyHash == bytes32(0)) revert ZeroField();
        Record storage prior = records[msg.sender][agentKey][reportHash];
        if (prior.exists) {
            if (prior.policyHash != policyHash || prior.previousReportHash != previousReportHash) {
                revert ConflictingReport();
            }
            return prior.sequence;
        }
        Head storage current = heads[msg.sender][agentKey];
        if (current.reportHash != previousReportHash) revert PreviousHashMismatch();
        sequence = current.sequence + 1;
        records[msg.sender][agentKey][reportHash] = Record(true, policyHash, previousReportHash, sequence);
        current.reportHash = reportHash;
        current.sequence = sequence;
        emit ReportAnchored(msg.sender, agentKey, reportHash, policyHash, previousReportHash, sequence);
    }

    function head(address evaluator, bytes32 agentKey) external view returns (bytes32 reportHash, uint64 sequence) {
        Head storage current = heads[evaluator][agentKey];
        return (current.reportHash, current.sequence);
    }

    function lookup(address evaluator, bytes32 agentKey, bytes32 reportHash)
        external
        view
        returns (bool exists, bytes32 policyHash, bytes32 previousReportHash, uint64 sequence)
    {
        Record storage record = records[evaluator][agentKey][reportHash];
        return (record.exists, record.policyHash, record.previousReportHash, record.sequence);
    }
}
