// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ProtocolVersion} from "../src/ProtocolVersion.sol";

contract ProtocolVersionTest {
    function testProtocolVersion() public pure {
        require(ProtocolVersion.VERSION == 1, "unexpected protocol version");
    }
}
