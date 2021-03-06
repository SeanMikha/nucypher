import pytest
from eth_tester.exceptions import TransactionFailed

from nucypher.blockchain.eth.actors import Bidder
from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterface


def test_create_bidder(testerchain, test_registry, agency, token_economics):
    bidder_address = testerchain.unassigned_accounts[0]
    bidder = Bidder(checksum_address=bidder_address, registry=test_registry)
    assert bidder.checksum_address == bidder_address
    assert bidder.registry == test_registry

    assert not bidder.get_deposited_eth
    assert not bidder.completed_work
    assert not bidder.remaining_work
    assert not bidder.refunded_work


def test_bidding(testerchain, agency, token_economics, test_registry):
    bidder_address = testerchain.unassigned_accounts[0]
    big_bid = token_economics.maximum_allowed_locked // 100
    bidder = Bidder(checksum_address=bidder_address, registry=test_registry)

    assert bidder.get_deposited_eth == 0
    receipt = bidder.place_bid(value=big_bid)
    assert receipt['status'] == 1
    assert bidder.get_deposited_eth == big_bid

    another_bidder_address = testerchain.unassigned_accounts[1]
    another_bid = token_economics.maximum_allowed_locked // 50
    another_bidder = Bidder(checksum_address=another_bidder_address, registry=test_registry)
    assert another_bidder.get_deposited_eth == 0
    receipt = another_bidder.place_bid(value=another_bid)
    assert receipt['status'] == 1
    assert another_bidder.get_deposited_eth == another_bid


def test_cancel_bid(testerchain, agency, token_economics, test_registry):
    bidder_address = testerchain.unassigned_accounts[1]
    bidder = Bidder(checksum_address=bidder_address, registry=test_registry)
    assert bidder.get_deposited_eth        # Bid
    receipt = bidder.cancel_bid()    # Cancel
    assert receipt['status'] == 1
    assert not bidder.get_deposited_eth    # No more bid

    # Can't cancel a bid twice in a row
    with pytest.raises((TransactionFailed, ValueError)):
        _receipt = bidder.cancel_bid()


def test_get_remaining_work(testerchain, agency, token_economics, test_registry):
    bidder_address = testerchain.unassigned_accounts[0]
    bidder = Bidder(checksum_address=bidder_address, registry=test_registry)
    remaining = bidder.remaining_work
    assert remaining


def test_claim(testerchain, agency, token_economics, test_registry):
    bidder_address = testerchain.unassigned_accounts[0]
    bidder = Bidder(checksum_address=bidder_address, registry=test_registry)
    with pytest.raises(Bidder.BiddingIsOpen):
        _receipt = bidder.claim()

    # Wait until the bidding window closes...
    testerchain.time_travel(seconds=token_economics.bidding_duration+1)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)

    # Ensure that the bidder is not staking.
    locked_tokens = staking_agent.get_locked_tokens(staker_address=bidder.checksum_address, periods=10)
    assert locked_tokens == 0

    receipt = bidder.claim()
    assert receipt['status'] == 1

    # Cant claim more than once
    with pytest.raises(Bidder.BidderError):
        _receipt = bidder.claim()

    assert bidder.get_deposited_eth == 40000000000000000000000
    assert bidder.completed_work == 0
    assert bidder.remaining_work == 500000000000000000000000
    assert bidder.refunded_work == 0

    # Ensure that the claimant is now the holder of an unbonded stake.
    locked_tokens = staking_agent.get_locked_tokens(staker_address=bidder.checksum_address, periods=10)
    assert locked_tokens == 1000000000000000000000000

    # Confirm the stake is unbonded
    worker_address = staking_agent.get_worker_from_staker(staker_address=bidder.checksum_address)
    assert worker_address == BlockchainInterface.NULL_ADDRESS
