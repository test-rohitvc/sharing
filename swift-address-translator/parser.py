import pandas as pd

from data_structuring.components.runners import ResultPostProcessing
from data_structuring.config import (
    CRFConfig,
    FuzzyMatchConfig,
    PostProcessingConfig,
    DatabaseConfig,
)
from data_structuring.run import AddressStructuringPipeline

# Load the CSV file containing the input addresses
data = pd.read_csv("./resources/input/addresses_gauntlet.csv")
# Extract the input addresses as a list object
addresses = data["address"].tolist()

from data_structuring.components.readers.base_reader import BaseReader, AddressSample

class ListReader(BaseReader):
    def __init__(self, addresses):
        self.addresses = addresses
    def read(self):
        for address in self.addresses:
            yield AddressSample(text=address)

reader = ListReader(addresses)

# Default configurations will be used, but these can be overwritten easily
# Refer to the documentation of each of these configuration classes for more
# information
crf_config = CRFConfig()
fuzzy_match_config = FuzzyMatchConfig()
post_processing_config = PostProcessingConfig()
database_config = DatabaseConfig()

# `DataStructuring` is the main class to interact with
# the package and perform inference
ds = AddressStructuringPipeline(
    crf_config=crf_config,
    fuzzy_match_config=fuzzy_match_config,
    post_processing_config=post_processing_config,
    database_config=database_config,
)

# This runs the inference on the gauntlet samples
results = ds.run(reader, batch_size=1024)

# Optionally, save the results as a human-readable CSV file
final_df, saved_path = ResultPostProcessing.save_list_as_human_readable_csv(
    results, file_name=f"data_structuring_output.csv", verbose=False
)
# set 'verbose' to True to enable
# explainability features
