// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @notice Immutable business records keyed by the actual caller and task request.
contract DemoRecordRegistry {
    error ZeroField();
    error DuplicateRequest();

    mapping(address => mapping(bytes32 => bytes32)) private records;

    event RecordAnchored(address indexed executor, bytes32 indexed requestId, bytes32 recordHash);

    function anchorRecord(bytes32 requestId, bytes32 recordHash) external {
        if (requestId == bytes32(0) || recordHash == bytes32(0)) revert ZeroField();
        if (records[msg.sender][requestId] != bytes32(0)) revert DuplicateRequest();
        records[msg.sender][requestId] = recordHash;
        emit RecordAnchored(msg.sender, requestId, recordHash);
    }

    function getRecord(address executor, bytes32 requestId) external view returns (bool exists, bytes32 recordHash) {
        recordHash = records[executor][requestId];
        exists = recordHash != bytes32(0);
    }
}
