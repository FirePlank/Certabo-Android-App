import pandas as pd

# read csv file in chunks
chunksize = 10 ** 6
for chunk in pd.read_csv('lichess_db_puzzle.csv', chunksize=chunksize, on_bad_lines='skip', dtype='unicode', low_memory=False):
    chunk = chunk[int(chunk["Rating"]) >= 1750 & int(chunk["Rating"]) <= 2600]
    
    # write to csv
    chunk.to_csv('lichess_db_filtered.csv', mode='a', header=False, index=False)