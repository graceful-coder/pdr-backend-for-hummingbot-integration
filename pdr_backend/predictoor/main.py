import time
import os
import time
import os
import threading
from datetime import datetime, timedelta, timezone
from threading import Thread

from pdr_backend.predictoor.predict import predict_function
from pdr_backend.utils.subgraph import get_all_interesting_prediction_contracts
from pdr_backend.utils.contract import PredictorContract, Web3Config


last_block_time = 0
topics = []

# TODO - check for all envs
assert os.environ.get("RPC_URL", None), "You must set RPC_URL environment variable"
assert os.environ.get(
    "SUBGRAPH_URL", None
), "You must set SUBGRAPH_URL environment variable"
web3_config = Web3Config(os.environ.get("RPC_URL"), os.environ.get("PRIVATE_KEY"))
owner = web3_config.owner


def process_block(block):
    global topics
    """ Process each contract and if needed, get a prediction, submit it and claim revenue for past epoch """
    if not topics:
        topics = get_all_interesting_prediction_contracts(
            os.environ.get("SUBGRAPH_URL"),
            os.environ.get("PAIR_FILTER", None),
            os.environ.get("TIMEFRAME_FILTER", None),
            os.environ.get("SOURCE_FILTER", None),
            os.environ.get("OWNER_ADDRS", None),
        )
    print(f"Got new block: {block['number']} with {len(topics)} topics")
    for address in topics:
        topic = topics[address]
        predictor_contract = PredictorContract(web3_config, address)
        epoch = predictor_contract.get_current_epoch()
        seconds_per_epoch = predictor_contract.get_secondsPerEpoch()
        seconds_till_epoch_end = (
            epoch * seconds_per_epoch + seconds_per_epoch - block["timestamp"]
        )
        print(
            f"\t{topic['name']} (at address {topic['address']} is at epoch {epoch}, seconds_per_epoch: {seconds_per_epoch}, seconds_till_epoch_end: {seconds_till_epoch_end}"
        )
        if epoch > topic["last_submited_epoch"] and seconds_till_epoch_end <= int(
            os.getenv("SECONDS_TILL_EPOCH_END", 5)
        ):
            """Try to estimate timestamp of prediction"""
            target_time = (epoch + 2) * seconds_per_epoch

            """ Let's fetch the prediction """
            (predicted_value, predicted_confidence) = predict_function(
                topic, target_time
            )
            if predicted_value is not None and predicted_confidence > 0:
                """We have a prediction, let's submit it"""
                stake_amount = os.getenv("STAKE_AMOUNT", 1) * predicted_confidence / 100 # TODO have a customizable function to handle this
                print(
                    f"Contract:{predictor_contract.contract_address} - Submiting prediction for slot:{target_time}"
                )
                predictor_contract.submit_prediction(
                    predicted_value, stake_amount, target_time, False
                )
            else:
                print(
                    f"We do not submit, prediction function returned ({predicted_value}, {predicted_confidence})"
                )
            # let's get the payout for previous epoch.  We don't care if it fails...
            slot = epoch * seconds_per_epoch - seconds_per_epoch
            print(
                f"Contract:{predictor_contract.contract_address} - Claiming revenue for slot:{slot}"
            )
            predictor_contract.payout(slot, False)
            # update topics
            topics[address]["last_submited_epoch"] = epoch


def log_loop(blockno):
    global last_block_time
    block = web3_config.w3.eth.get_block(blockno, full_transactions=False)
    if block:
        last_block_time = block["timestamp"]
        process_block(block)


def main():
    print("Starting main loop...")
    lastblock = 0
    while True:
        block = web3_config.w3.eth.block_number
        if block > lastblock:
            lastblock = block
            log_loop(block)
        else:
            time.sleep(1)


if __name__ == "__main__":
    main()
