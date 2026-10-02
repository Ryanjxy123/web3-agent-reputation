// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {DemoAgentRegistry} from "../src/DemoAgentRegistry.sol";
import {DemoRecordRegistry} from "../src/DemoRecordRegistry.sol";
import {EvaluationAnchor} from "../src/EvaluationAnchor.sol";

interface Vm {
    struct Log {
        bytes32[] topics;
        bytes data;
        address emitter;
    }
    function prank(address) external;
    function expectRevert(bytes4) external;
    function recordLogs() external;
    function getRecordedLogs() external returns (Log[] memory);
    function assume(bool) external;
}

contract DemoContractsTest {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    address private constant OWNER = address(0xA11CE);
    address private constant EXECUTOR = address(0xB0B);
    address private constant EVALUATOR = address(0xEAA);
    bytes32 private constant REQUEST = keccak256("request");
    bytes32 private constant DIGEST = keccak256("record");
    bytes32 private constant AGENT = keccak256("agent");
    bytes32 private constant POLICY = keccak256("policy");
    DemoAgentRegistry private registry;
    DemoRecordRegistry private records;
    EvaluationAnchor private anchor;

    function setUp() public {
        registry = new DemoAgentRegistry(keccak256("test-instance"));
        records = new DemoRecordRegistry();
        anchor = new EvaluationAnchor();
        anchor.setEvaluator(EVALUATOR, true);
    }

    function registerAgent() private returns (uint256) {
        vm.prank(OWNER);
        return registry.register("http://fixture-a:9101/capabilities");
    }

    function testRegistryRegistrationAndRevisionEvents() public {
        vm.recordLogs();
        uint256 id = registerAgent();
        require(id == 1 && registry.ownerOf(id) == OWNER);
        require(registry.revisionOf(id) == 1);
        require(registry.deploymentInstanceId() == keccak256("test-instance"));
        Vm.Log[] memory logs = vm.getRecordedLogs();
        require(logs.length == 1 && logs[0].emitter == address(registry));
        require(logs[0].topics[0] == keccak256("AgentRegistered(uint256,address,string,uint64)"));
        require(logs[0].topics[1] == bytes32(id));
        require(logs[0].topics[2] == bytes32(uint256(uint160(OWNER))));
        (string memory uri, uint64 revision) = abi.decode(logs[0].data, (string, uint64));
        require(keccak256(bytes(uri)) == keccak256(bytes(registry.agentURI(id))) && revision == 1);
        vm.prank(OWNER);
        registry.setAgentURI(id, "data:application/json,{}");
        require(registry.revisionOf(id) == 2);
        vm.prank(OWNER);
        registry.setDeclaredExecutor(id, EXECUTOR);
        require(registry.declaredExecutorOf(id) == EXECUTOR && registry.revisionOf(id) == 3);
    }

    function testTransferInvalidatesDeclaredExecutorAndOldOwner() public {
        uint256 id = registerAgent();
        vm.prank(OWNER);
        registry.setDeclaredExecutor(id, EXECUTOR);
        vm.prank(OWNER);
        registry.transferOwnership(id, EXECUTOR);
        require(registry.ownerOf(id) == EXECUTOR);
        require(registry.declaredExecutorOf(id) == address(0) && registry.revisionOf(id) == 3);
        vm.prank(OWNER);
        vm.expectRevert(DemoAgentRegistry.NotOwner.selector);
        registry.setAgentURI(id, "obsolete");
        vm.prank(EXECUTOR);
        registry.setAgentURI(id, "new-owner-uri");
        require(registry.revisionOf(id) == 4);
    }

    function testUnknownIdentityAndUnauthorizedChanges() public {
        vm.expectRevert(DemoAgentRegistry.UnknownAgent.selector);
        registry.ownerOf(1);
        uint256 id = registerAgent();
        vm.expectRevert(DemoAgentRegistry.NotOwner.selector);
        registry.setAgentURI(id, "attacker-uri");
        vm.expectRevert(DemoAgentRegistry.NotOwner.selector);
        registry.setDeclaredExecutor(id, EXECUTOR);
        vm.expectRevert(DemoAgentRegistry.NotOwner.selector);
        registry.transferOwnership(id, EXECUTOR);
    }

    function testRegistryRejectsZeroDeploymentInstance() public {
        vm.expectRevert(DemoAgentRegistry.ZeroField.selector);
        new DemoAgentRegistry(bytes32(0));
    }

    function testRegistryZeroAndOversizedFields() public {
        vm.expectRevert(DemoAgentRegistry.InvalidURI.selector);
        registry.register("");
        vm.expectRevert(DemoAgentRegistry.InvalidURI.selector);
        registry.register(string(new bytes(4097)));
        uint256 id = registerAgent();
        vm.prank(OWNER);
        vm.expectRevert(DemoAgentRegistry.ZeroField.selector);
        registry.setDeclaredExecutor(id, address(0));
        vm.prank(OWNER);
        vm.expectRevert(DemoAgentRegistry.ZeroField.selector);
        registry.transferOwnership(id, address(0));
    }

    function testRecordEventAndReadBack() public {
        vm.recordLogs();
        vm.prank(EXECUTOR);
        records.anchorRecord(REQUEST, DIGEST);
        (bool exists, bytes32 digest) = records.getRecord(EXECUTOR, REQUEST);
        require(exists && digest == DIGEST);
        Vm.Log[] memory logs = vm.getRecordedLogs();
        require(logs.length == 1 && logs[0].emitter == address(records));
        require(logs[0].topics[0] == keccak256("RecordAnchored(address,bytes32,bytes32)"));
        require(logs[0].topics[1] == bytes32(uint256(uint160(EXECUTOR))));
        require(logs[0].topics[2] == REQUEST && abi.decode(logs[0].data, (bytes32)) == DIGEST);
    }

    function testDuplicateRecordNeverOverwritesEvenSameDigest() public {
        vm.prank(EXECUTOR);
        records.anchorRecord(REQUEST, DIGEST);
        vm.prank(EXECUTOR);
        vm.expectRevert(DemoRecordRegistry.DuplicateRequest.selector);
        records.anchorRecord(REQUEST, DIGEST);
        vm.prank(EXECUTOR);
        vm.expectRevert(DemoRecordRegistry.DuplicateRequest.selector);
        records.anchorRecord(REQUEST, bytes32(uint256(123)));
        (, bytes32 digest) = records.getRecord(EXECUTOR, REQUEST);
        require(digest == DIGEST);
    }

    function testRecordZeroFieldsAndExecutorIsolation() public {
        vm.expectRevert(DemoRecordRegistry.ZeroField.selector);
        records.anchorRecord(bytes32(0), DIGEST);
        vm.expectRevert(DemoRecordRegistry.ZeroField.selector);
        records.anchorRecord(REQUEST, bytes32(0));
        vm.prank(OWNER);
        records.anchorRecord(REQUEST, DIGEST);
        (bool exists,) = records.getRecord(EXECUTOR, REQUEST);
        require(!exists);
        vm.prank(EXECUTOR);
        records.anchorRecord(REQUEST, POLICY);
        (, bytes32 ownerHash) = records.getRecord(OWNER, REQUEST);
        (, bytes32 executorHash) = records.getRecord(EXECUTOR, REQUEST);
        require(ownerHash == DIGEST && executorHash == POLICY);
    }

    function testFuzzRecordImmutability(bytes32 requestId, bytes32 digest) public {
        vm.assume(requestId != bytes32(0) && digest != bytes32(0));
        records.anchorRecord(requestId, digest);
        vm.expectRevert(DemoRecordRegistry.DuplicateRequest.selector);
        records.anchorRecord(requestId, digest);
        (bool exists, bytes32 actual) = records.getRecord(address(this), requestId);
        require(exists && actual == digest);
    }

    function testAnchorAuthorizationAndRevocation() public {
        vm.expectRevert(EvaluationAnchor.Unauthorized.selector);
        anchor.anchorReport(AGENT, DIGEST, POLICY, bytes32(0));
        vm.prank(EXECUTOR);
        vm.expectRevert(EvaluationAnchor.Unauthorized.selector);
        anchor.setEvaluator(EXECUTOR, true);
        anchor.setEvaluator(EVALUATOR, false);
        vm.prank(EVALUATOR);
        vm.expectRevert(EvaluationAnchor.Unauthorized.selector);
        anchor.anchorReport(AGENT, DIGEST, POLICY, bytes32(0));
    }

    function testAnchorEventsAndMonotonicForwardChain() public {
        vm.recordLogs();
        vm.prank(EVALUATOR);
        require(anchor.anchorReport(AGENT, DIGEST, POLICY, bytes32(0)) == 1);
        Vm.Log[] memory logs = vm.getRecordedLogs();
        require(logs.length == 1 && logs[0].emitter == address(anchor));
        require(logs[0].topics[0] == keccak256("ReportAnchored(address,bytes32,bytes32,bytes32,bytes32,uint64)"));
        require(logs[0].topics[1] == bytes32(uint256(uint160(EVALUATOR))));
        require(logs[0].topics[2] == AGENT && logs[0].topics[3] == DIGEST);
        (bytes32 policy, bytes32 previous, uint64 sequence) = abi.decode(logs[0].data, (bytes32, bytes32, uint64));
        require(policy == POLICY && previous == bytes32(0) && sequence == 1);
        vm.prank(EVALUATOR);
        vm.expectRevert(EvaluationAnchor.PreviousHashMismatch.selector);
        anchor.anchorReport(AGENT, REQUEST, POLICY, bytes32(0));
        vm.prank(EVALUATOR);
        require(anchor.anchorReport(AGENT, REQUEST, POLICY, DIGEST) == 2);
        (bytes32 headHash, uint64 headSequence) = anchor.head(EVALUATOR, AGENT);
        require(headHash == REQUEST && headSequence == 2);
    }

    function testAnchorDuplicateIsIdempotentAfterHeadAdvances() public {
        vm.prank(EVALUATOR);
        anchor.anchorReport(AGENT, DIGEST, POLICY, bytes32(0));
        vm.prank(EVALUATOR);
        anchor.anchorReport(AGENT, REQUEST, POLICY, DIGEST);
        vm.recordLogs();
        vm.prank(EVALUATOR);
        require(anchor.anchorReport(AGENT, DIGEST, POLICY, bytes32(0)) == 1);
        require(vm.getRecordedLogs().length == 0);
        (bytes32 headHash, uint64 sequence) = anchor.head(EVALUATOR, AGENT);
        require(headHash == REQUEST && sequence == 2);
        vm.prank(EVALUATOR);
        vm.expectRevert(EvaluationAnchor.ConflictingReport.selector);
        anchor.anchorReport(AGENT, DIGEST, REQUEST, bytes32(0));
        vm.prank(EVALUATOR);
        vm.expectRevert(EvaluationAnchor.ConflictingReport.selector);
        anchor.anchorReport(AGENT, DIGEST, POLICY, REQUEST);
        (bool exists, bytes32 policy, bytes32 previous, uint64 originalSequence) =
            anchor.lookup(EVALUATOR, AGENT, DIGEST);
        require(exists && policy == POLICY && previous == bytes32(0) && originalSequence == 1);
    }

    function testAnchorPublisherAndAgentIsolation() public {
        anchor.setEvaluator(OWNER, true);
        vm.prank(EVALUATOR);
        anchor.anchorReport(AGENT, DIGEST, POLICY, bytes32(0));
        vm.prank(OWNER);
        require(anchor.anchorReport(AGENT, DIGEST, REQUEST, bytes32(0)) == 1);
        vm.prank(EVALUATOR);
        require(anchor.anchorReport(REQUEST, DIGEST, POLICY, bytes32(0)) == 1);
        (, bytes32 ownerPolicy,,) = anchor.lookup(OWNER, AGENT, DIGEST);
        (, bytes32 evaluatorPolicy,,) = anchor.lookup(EVALUATOR, AGENT, DIGEST);
        require(ownerPolicy == REQUEST && evaluatorPolicy == POLICY);
    }

    function testAnchorRejectsZeroFields() public {
        vm.expectRevert(EvaluationAnchor.ZeroField.selector);
        anchor.setEvaluator(address(0), true);
        vm.prank(EVALUATOR);
        vm.expectRevert(EvaluationAnchor.ZeroField.selector);
        anchor.anchorReport(bytes32(0), DIGEST, POLICY, bytes32(0));
        vm.prank(EVALUATOR);
        vm.expectRevert(EvaluationAnchor.ZeroField.selector);
        anchor.anchorReport(AGENT, bytes32(0), POLICY, bytes32(0));
        vm.prank(EVALUATOR);
        vm.expectRevert(EvaluationAnchor.ZeroField.selector);
        anchor.anchorReport(AGENT, DIGEST, bytes32(0), bytes32(0));
    }
}
