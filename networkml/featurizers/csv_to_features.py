import argparse
import csv
import concurrent.futures
import datetime
import gzip
import humanize
import io
import logging
import numpy as np
import os
import sys
import time

from networkml.featurizers.main import Featurizer


class CSVToFeatures():


    def __init__(self):
        self.logger = logging.getLogger(__name__)


    @staticmethod
    def write_features_to_csv(header, rows, out_file, gzip_opt):
        if gzip_opt in ['output', 'both']:
            with gzip.open(out_file, 'wb') as f:
                w = csv.DictWriter(io.TextIOWrapper(f, newline='', write_through=True), fieldnames=header)
                w.writeheader()
                w.writerows(rows)
        else:
            with open(out_file, 'w') as f:
                w = csv.DictWriter(f, fieldnames=header)
                w.writeheader()
                w.writerows(rows)


    @staticmethod
    def combine_csvs(out_paths, combined_path, gzip_opt):
        # First determine the field names from the top line of each input file
        fieldnames = []
        for filename in out_paths:
            if gzip_opt in ['output', 'both']:
                with gzip.open(filename, 'rb') as f_in:
                    reader = csv.reader(io.TextIOWrapper(f_in, newline=''))
                    headers = next(reader)
                    for h in headers:
                        if h not in fieldnames:
                            fieldnames.append(h)
            else:
                with open(filename, 'r') as f_in:
                    reader = csv.reader(f_in)
                    headers = next(reader)
                    for h in headers:
                        if h not in fieldnames:
                            fieldnames.append(h)

        fieldnames.append('filename')
        # Then copy the data
        if gzip_opt in ['output', 'both']:
            with gzip.open(combined_path, 'wb') as f_out:
                writer = csv.DictWriter(io.TextIOWrapper(f_out, newline='', write_through=True), fieldnames=fieldnames)
                writer.writeheader()
                for filename in out_paths:
                    with gzip.open(filename, 'rb') as f_in:
                        reader = csv.DictReader(io.TextIOWrapper(f_in, newline=''))
                        for line in reader:
                            line['filename'] = filename.split('/')[-1].split('.features.gz')[0]
                            writer.writerow(line)
                        CSVToFeatures.cleanup_files([filename])
        else:
            with open(combined_path, 'w') as f_out:
                writer = csv.DictWriter(f_out, fieldnames=fieldnames)
                writer.writeheader()
                for filename in out_paths:
                    with open(filename, 'r') as f_in:
                        reader = csv.DictReader(f_in)
                        for line in reader:
                            line['filename'] = filename.split('/')[-1].split('.features')[0]
                            writer.writerow(line)
                        CSVToFeatures.cleanup_files([filename])


    @staticmethod
    def cleanup_files(paths):
        for fi in paths:
            if os.path.exists(fi):
                os.remove(fi)


    @staticmethod
    def get_rows(in_file, gzip_opt):
        rows = []
        if gzip_opt in ['input', 'both']:
            with gzip.open(in_file, 'rb') as f_in:
                reader = csv.DictReader(io.TextIOWrapper(f_in, newline=''))
                for line in reader:
                    rows.append(dict(line))
        else:
            with open(in_file, 'r') as f_in:
                reader = csv.DictReader(f_in)
                for line in reader:
                    rows.append(dict(line))
        return rows

    @staticmethod
    def parse_args(parser):
        parser.add_argument('path', help='path to a single gzipped csv file, or a directory of gzipped csvs to parse')
        parser.add_argument('--combined', '-c', action='store_true', help='write out all records from all csvs into a single gzipped csv file')
        parser.add_argument('--features_path', '-p', default='./networkml/featurizers/funcs', help='path to featurizer functions (default="./networkml/featurizers/funcs")')
        parser.add_argument('--functions', '-f', default='', help='comma separated list of <class>:<function> to featurize (default=None)')
        parser.add_argument('--groups', '-g', default='default', help='comma separated list of groups of functions to featurize (default=default)')
        parser.add_argument('--gzip', '-z', choices=['input', 'output', 'both', 'neither'], default='both', help='gzip the input/output file, both other neither (default=both)')
        parser.add_argument('--logging', '-l', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], default='INFO', help='logging level (default=INFO)')
        parser.add_argument('--output', '-o', default=None, help='path to write out gzipped csv file or directory for gzipped csv files')
        parser.add_argument('--threads', '-t', default=1, type=int, help='number of async threads to use (default=1)')
        parsed_args = parser.parse_args()
        return parsed_args

    def exec_features(self, features, in_file, out_file, features_path, gzip_opt):
        self.logger.info(f'Processing {in_file}')
        rows = CSVToFeatures.get_rows(in_file, gzip_opt)
        featurizer = Featurizer()
        rows = featurizer.main(features, rows, features_path)

        header = set()
        for row in rows:
            for r in row:
                header.update(r.keys())
        header = list(header)

        columns = []
        for row in rows:
            columns.append(np.array(row))
        np_array = np.vstack(columns)

        rows = None
        for method in np_array:
            if rows is None:
                rows = method
            else:
                for i, row in enumerate(method):
                    rows[i].update(row)
        rows = rows.tolist()

        if header and rows:
            CSVToFeatures.write_features_to_csv(header, rows, out_file, gzip_opt)
        else:
            self.logger.warning(f'No results based on {features} for {in_file}')

    def process_files(self, threads, features, features_path, in_paths, out_paths, gzip_opt):
        num_files = len(in_paths)
        finished_files = 0
        # corner case so it works in jupyterlab
        failed_paths = []
        if threads < 2:
            for i in range(len(in_paths)):
                try:
                    finished_files += 1
                    self.exec_features(features, in_paths[i], out_paths[i], features_path, gzip_opt)
                    self.logger.info(f'Finished {in_paths[i]}. {finished_files}/{num_files} CSVs done.')
                except Exception as e:
                    self.logger.error(f'{in_paths[i]} generated an exception: {e}')
                    failed_paths.append(out_paths[i])
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=threads) as executor:
                future_to_parse = {executor.submit(self.exec_features, features, in_paths[i], out_paths[i], features_path, gzip_opt): i for i in range(len((in_paths)))}
                for future in concurrent.futures.as_completed(future_to_parse):
                    path = future_to_parse[future]
                    try:
                        finished_files += 1
                        future.result()
                    except Exception as e:
                        self.logger.error(f'{in_paths[path]} generated an exception: {e}')
                        failed_paths.append(out_paths[path])
                    else:
                        self.logger.info(f'Finished {in_paths[path]}. {finished_files}/{num_files} CSVs done.')
        return failed_paths


    def main(self):
        parsed_args = CSVToFeatures.parse_args(argparse.ArgumentParser())
        in_path = parsed_args.path
        out_path = parsed_args.output
        combined = parsed_args.combined
        features_path = parsed_args.features_path
        threads = parsed_args.threads
        log_level = parsed_args.logging
        functions = parsed_args.functions
        groups = parsed_args.groups
        gzip_opt = parsed_args.gzip
        if not groups and not functions:
            self.logger.warning('No groups or functions were selected, quitting')
            return

        log_levels = {'INFO': logging.INFO, 'DEBUG': logging.DEBUG, 'WARNING': logging.WARNING, 'ERROR': logging.ERROR}
        logging.basicConfig(level=log_levels[log_level])

        in_paths = []
        out_paths = []

        # parse out features dict
        groups = tuple(groups.split(','))
        funcs = functions.split(',')
        functions = []
        for function in funcs:
            functions.append(tuple(function.split(':')))
        features = {'groups': groups, 'functions': functions}

        # check if it's a directory or a file
        if os.path.isdir(in_path):
            if out_path:
                pathlib.Path(out_path).mkdir(parents=True, exist_ok=True)
            for root, _, files in os.walk(in_path):
                for pathfile in files:
                    in_paths.append(os.path.join(root, pathfile))
                    if out_path:
                        if gzip_opt in ['neither', 'input']:
                            out_paths.append(os.path.join(out_path, pathfile) + ".features")
                        else:
                            out_paths.append(os.path.join(out_path, pathfile) + ".features.gz")
                    else:
                        if gzip_opt in ['neither', 'input']:
                            out_paths.append(os.path.join(root, pathfile) + ".features")
                        else:
                            out_paths.append(os.path.join(root, pathfile) + ".features.gz")
        else:
            in_paths.append(in_path)
            if out_path:
                out_paths.append(out_path)
            else:
                if gzip_opt in ['neither', 'input']:
                    out_paths.append(in_path + ".features")
                else:
                    out_paths.append(in_path + ".features.gz")

        failed_paths = self.process_files(threads, features, features_path, in_paths, out_paths, gzip_opt)

        for failed_path in failed_paths:
            if failed_path in out_paths:
                out_paths.remove(failed_path)

        if combined:
            combined_path = os.path.join(os.path.dirname(out_paths[0]), "combined.csv.gz")
            if gzip_opt in ['input', 'neither']:
                combined_path = combined_path[:-3]
            self.logger.info(f'Combining CSVs into a single file: {combined_path}')
            CSVToFeatures.combine_csvs(out_paths, combined_path, gzip_opt)
        else:
            self.logger.info(f'GZipped CSV file(s) written out to: {out_paths}')


if __name__ == '__main__':
    start = time.time()
    instance = CSVToFeatures()
    instance.main()
    end = time.time()
    elapsed = end - start
    human_elapsed = humanize.naturaldelta(datetime.timedelta(seconds=elapsed))
    logging.info(f'Elapsed Time: {elapsed} seconds ({human_elapsed})')
