// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @notice Local demonstration identity registry, not ERC-721 or ERC-8004.
contract DemoAgentRegistry {
    error ZeroField();
    error InvalidURI();
    error UnknownAgent();
    error NotOwner();

    struct Agent {
        address owner;
        address executor;
        uint64 revision;
        string uri;
    }

    bytes32 public immutable deploymentInstanceId;
    uint256 public nextAgentId = 1;
    mapping(uint256 => Agent) private agents;

    event AgentRegistered(uint256 indexed agentId, address indexed owner, string uri, uint64 revision);
    event AgentURIUpdated(uint256 indexed agentId, string uri, uint64 revision);
    event DeclaredExecutorUpdated(uint256 indexed agentId, address indexed executor, uint64 revision);
    event AgentOwnershipTransferred(
        uint256 indexed agentId, address indexed previousOwner, address indexed newOwner, uint64 revision
    );

    constructor(bytes32 instanceId) {
        if (instanceId == bytes32(0)) revert ZeroField();
        deploymentInstanceId = instanceId;
    }

    function register(string calldata uri) external returns (uint256 agentId) {
        _checkURI(uri);
        agentId = nextAgentId++;
        agents[agentId] = Agent(msg.sender, address(0), 1, uri);
        emit AgentRegistered(agentId, msg.sender, uri, 1);
    }

    function ownerOf(uint256 agentId) external view returns (address) {
        return _agent(agentId).owner;
    }

    function agentURI(uint256 agentId) external view returns (string memory) {
        return _agent(agentId).uri;
    }

    function revisionOf(uint256 agentId) external view returns (uint64) {
        return _agent(agentId).revision;
    }

    function declaredExecutorOf(uint256 agentId) external view returns (address) {
        return _agent(agentId).executor;
    }

    function setAgentURI(uint256 agentId, string calldata uri) external {
        Agent storage agent = _owned(agentId);
        _checkURI(uri);
        agent.uri = uri;
        emit AgentURIUpdated(agentId, uri, ++agent.revision);
    }

    function setDeclaredExecutor(uint256 agentId, address executor) external {
        Agent storage agent = _owned(agentId);
        if (executor == address(0)) revert ZeroField();
        agent.executor = executor;
        emit DeclaredExecutorUpdated(agentId, executor, ++agent.revision);
    }

    function transferOwnership(uint256 agentId, address newOwner) external {
        Agent storage agent = _owned(agentId);
        if (newOwner == address(0)) revert ZeroField();
        address previous = agent.owner;
        agent.owner = newOwner;
        agent.executor = address(0);
        emit AgentOwnershipTransferred(agentId, previous, newOwner, ++agent.revision);
    }

    function _agent(uint256 agentId) private view returns (Agent storage agent) {
        agent = agents[agentId];
        if (agent.owner == address(0)) revert UnknownAgent();
    }

    function _owned(uint256 agentId) private view returns (Agent storage agent) {
        agent = _agent(agentId);
        if (agent.owner != msg.sender) revert NotOwner();
    }

    function _checkURI(string calldata uri) private pure {
        if (bytes(uri).length == 0 || bytes(uri).length > 4096) revert InvalidURI();
    }
}
