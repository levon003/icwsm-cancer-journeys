#!/usr/bin/env python
# Python 3 script to convert a JSON file to a Dataframe, writing it out as CSV and Feather formats

import os
import numpy as np
import pandas as pd

import matplotlib.pyplot as plt
import matplotlib.dates as md
import matplotlib
import pylab as pl

import datetime as dt
import time

from collections import Counter

import json
import os
import re
from html.parser import HTMLParser
import itertools
import multiprocessing as mp
import datetime as dt

from tqdm import tqdm

import pyarrow

raw_data_dir = "/home/srivbane/shared/caringbridge/data/raw"
raw_journal_filename = os.path.join(raw_data_dir, "journal.json")

working_dir = "/home/srivbane/shared/caringbridge/data/projects/qual-health-journeys/extract_site_features"
os.makedirs(working_dir, exist_ok=True)

flattened_journal_json_filename = os.path.join(working_dir, "journal_flat.json")
#flattened_journal_json_filename = "journal_flat_mini.json"

store_filename = os.path.join(working_dir, "store.h5")
parquet_journal_df_filename = os.path.join(working_dir, "journal.parquet")
feathered_journal_df_filename = os.path.join(working_dir, "journal.df")
csv_journal_df_filename = os.path.join(working_dir, "journal_flat.csv")

print(f"Opening store '{store_filename}'.")
store = pd.HDFStore(store_filename)

print(f"Opening file '{flattened_journal_json_filename}'.")
startTime = dt.datetime.now()
chunksize = 2**22
#chunksize = 10000
frames = []
with open(flattened_journal_json_filename, 'r', encoding="utf8") as infile:
    reader = pd.read_json(infile, orient="records", lines=True, chunksize=chunksize)
    print(f"Reader created. Iterating through chunks using chunksize {chunksize}...")
    for i, chunk in enumerate(reader):
        frames.append(chunk)
        elapsedTime = dt.datetime.now() - startTime
        print(f"{i}: Finished reading chunk {i} after {elapsedTime}.")
print(f"Concatenating {len(frames)} frames.")
df = pd.concat(frames, copy=False, ignore_index=True)

print(f"Writing dataframe to parquet file '{parquet_journal_df_filename}'.")
df.to_parquet(parquet_journal_df_filename)

print("Writing dataframe to hd5 store.")
try:
    store.put("journal", df, format="table")
    print(f"Written. Closing store after {dt.datetime.now() - startTime}.")
except:
    print("Failed writing to store.")
finally:
    store.close()

print(f"Saving unified dataframe to '{csv_journal_df_filename}'.")
df.to_csv(csv_journal_df_filename)

should_write_feather = False
dtype_error = False
for index in df.dtypes.index:
    dtype = str(df.dtypes[index])
    try:
        arrow_dtype = str(pyarrow.lib.array(df[index], from_pandas=True).type)
    except:
        print(f"Error converting column '{index}' of dtype '{dtype}' to a PyArrow type.")
        dtype_error = True
if should_write_feather and not dtype_error:
    print(f"Saving unified dataframe to '{feathered_journal_df_filename}'.")
    df.to_feather(feathered_journal_df_filename)
else:
    print("Skipping outputting to feather.")

endTime = dt.datetime.now()
print(f"Finished. Total lapsed time: {endTime - startTime}")

