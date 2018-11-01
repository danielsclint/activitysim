# ActivitySim
# See full license in LICENSE.txt.

from __future__ import (absolute_import, division, print_function, )
from future.standard_library import install_aliases
install_aliases()  # noqa: E402
from builtins import next
from builtins import range

import os
import logging
import logging.config
import sys
import time
import contextlib
from collections import OrderedDict

import yaml

import numpy as np
import pandas as pd

from activitysim.core import inject

from . import config


# Configurations
ASIM_LOGGER = 'activitysim'
CSV_FILE_TYPE = 'csv'
LOGGING_CONF_FILE_NAME = 'logging.yaml'


logger = logging.getLogger(__name__)


def extend_trace_label(trace_label, extension):
    if trace_label:
        trace_label = "%s.%s" % (trace_label, extension)
    return trace_label


def format_elapsed_time(t):
    return "%s seconds (%s minutes)" % (round(t, 3), round(t / 60.0, 1))


def print_elapsed_time(msg=None, t0=None, debug=False):
    t1 = time.time()
    if msg:
        assert t0 is not None
        t = t1 - (t0 or t1)
        msg = "Time to execute %s : %s" % (msg, format_elapsed_time(t))
        if debug:
            logger.debug(msg)
        else:
            logger.info(msg)
    return t1


def delete_output_files(file_type, ignore=None, subdir=None):
    """
    Delete files in output directory of specified type

    Parameters
    ----------
    output_dir: str
        Directory of trace output CSVs

    Returns
    -------
    Nothing
    """

    output_dir = inject.get_injectable('output_dir')

    if subdir:
        output_dir = os.path.join(output_dir, subdir)
        if not os.path.exists(output_dir):
            logger.warn("delete_output_files: No subdirectory %s" % (file_type, output_dir))
            return

    if ignore:
        ignore = [os.path.realpath(p) for p in ignore]

    logger.debug("Deleting %s files in output_dir %s" % (file_type, output_dir))

    for the_file in os.listdir(output_dir):
        if the_file.endswith(file_type):
            file_path = os.path.join(output_dir, the_file)

            if ignore and os.path.realpath(file_path) in ignore:
                logger.info("delete_output_files ignoring %s" % file_path)
                continue

            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(e)


def delete_csv_files():
    """
    Delete CSV files in output_dir

    Returns
    -------
    Nothing
    """
    delete_output_files(CSV_FILE_TYPE)


def config_logger(basic=False):
    """
    Configure logger

    look for conf file in configs_dir, if not found use basicConfig

    Returns
    -------
    Nothing
    """

    # look for conf file in configs_dir
    log_config_file = None
    if not basic:
        log_config_file = config.config_file_path(LOGGING_CONF_FILE_NAME, mandatory=False)

    if log_config_file:
        with open(log_config_file) as f:
            config_dict = yaml.load(f)
            config_dict = config_dict['logging']
            config_dict.setdefault('version', 1)
            logging.config.dictConfig(config_dict)
    else:
        logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    logger = logging.getLogger(ASIM_LOGGER)

    if log_config_file:
        logger.info("Read logging configuration from: %s" % log_config_file)
    else:
        print("Configured logging using basicConfig")
        logger.info("Configured logging using basicConfig")


def print_summary(label, df, describe=False, value_counts=False):
    """
    Print summary

    Parameters
    ----------
    label: str
        tracer name
    df: pandas.DataFrame
        traced dataframe
    describe: boolean
        print describe?
    value_counts: boolean
        print value counts?

    Returns
    -------
    Nothing
    """

    if not (value_counts or describe):
        logger.error("print_summary neither value_counts nor describe")

    if value_counts:
        logger.info("%s value counts:\n%s" % (label, df.value_counts()))

    if describe:
        logger.info("%s summary:\n%s" % (label, df.describe()))


def register_traceable_table(table_name, df):
    """
    Register traceable table

    Parameters
    ----------
    df: pandas.DataFrame
        traced dataframe

    Returns
    -------
    Nothing
    """

    trace_hh_id = inject.get_injectable("trace_hh_id", None)

    trace_injectable = 'trace_%s' % table_name
    new_traced_ids = []

    if trace_hh_id is None:
        return

    traceable_tables = inject.get_injectable('traceable_tables', [])
    if table_name not in traceable_tables:
        logger.error("table '%s' not in traceable_tables" % table_name)
        return

    idx_name = df.index.name
    if idx_name is None:
        logger.error("Can't register table '%s' without index name" % table_name)
        return

    traceable_table_refs = inject.get_injectable('traceable_table_refs', None)

    # traceable_table_refs is OrderedDict so we can find first registered table to slice by ref_con
    if traceable_table_refs is None:
        traceable_table_refs = OrderedDict()
    if idx_name in traceable_table_refs and traceable_table_refs[idx_name] != table_name:
        logger.error("table '%s' index name '%s' already registered for table '%s'" %
                     (table_name, idx_name, traceable_table_refs[idx_name]))
        return

    if table_name == 'households':
        if trace_hh_id not in df.index:
            logger.warning("trace_hh_id %s not in dataframe" % trace_hh_id)
            new_traced_ids = []
        else:
            logger.info("tracing household id %s in %s households" % (trace_hh_id, len(df.index)))
            new_traced_ids = [trace_hh_id]
    else:

        # find first already registered ref_col we can use to slice this table
        ref_con = next((c for c in traceable_table_refs if c in df.columns), None)
        if ref_con is None:
            logger.error("can't find a registered table to slice table '%s' index name '%s'"
                         " in traceable_table_refs: %s" %
                         (table_name, idx_name, traceable_table_refs))
            return

        # get traceable_ids for ref_con table
        ref_con_trace_injectable = 'trace_%s' % traceable_table_refs[ref_con]
        ref_con_traced_ids = inject.get_injectable(ref_con_trace_injectable, [])

        # inject list of ids in table we are tracing
        # this allows us to slice by id without requiring presence of a household id column
        traced_df = df[df[ref_con].isin(ref_con_traced_ids)]
        new_traced_ids = traced_df.index.tolist()
        if len(new_traced_ids) == 0:
            logger.warning("register %s: no rows with %s in %s." %
                           (table_name, ref_con, ref_con_traced_ids))

    # update traceable_table_refs with this traceable_table's ref_con
    if idx_name not in traceable_table_refs:
        traceable_table_refs[idx_name] = table_name
        print("adding table %s.%s to traceable_table_refs" % (table_name, idx_name))
        inject.add_injectable('traceable_table_refs', traceable_table_refs)

    # update the list of trace_ids for this table
    prior_traced_ids = inject.get_injectable(trace_injectable, [])
    if prior_traced_ids:
        logger.info("register %s: adding %s ids to %s existing trace ids" %
                    (table_name, len(new_traced_ids), len(prior_traced_ids)))
    traced_ids = prior_traced_ids + new_traced_ids
    logger.info("register %s: tracing ids %s in %s %s" %
                (table_name, traced_ids, len(df.index), table_name))
    if new_traced_ids:
        inject.add_injectable(trace_injectable, traced_ids)


def write_df_csv(df, file_path, index_label=None, columns=None, column_labels=None, transpose=True):

    mode = 'a' if os.path.isfile(file_path) else 'w'

    if columns:
        df = df[columns]

    if not transpose:
        df.to_csv(file_path, mode="a", index=df.index.name is not None, header=True)
        return

    df_t = df.transpose()
    if df.index.name is not None:
        df_t.index.name = df.index.name
    elif index_label:
        df_t.index.name = index_label

    with open(file_path, mode=mode) as f:
        if column_labels is None:
            column_labels = [None, None]
        if column_labels[0] is None:
            column_labels[0] = 'label'
        if column_labels[1] is None:
            column_labels[1] = 'value'

        if len(df_t.columns) == len(column_labels) - 1:
            column_label_row = ','.join(column_labels)
        else:
            column_label_row = \
                column_labels[0] + ',' \
                + ','.join([column_labels[1] + '_' + str(i+1) for i in range(len(df_t.columns))])

        if mode == 'a':
            column_label_row = '# ' + column_label_row
        f.write(column_label_row + '\n')
    df_t.to_csv(file_path, mode='a', index=True, header=True)


def write_series_csv(series, file_path, index_label=None, columns=None, column_labels=None):

    if isinstance(columns, str):
        series = series.rename(columns)
    elif isinstance(columns, list):
        if columns[0]:
            series.index.name = columns[0]
        series = series.rename(columns[1])
    if index_label and series.index.name is None:
        series.index.name = index_label
    series.to_csv(file_path, mode='a', index=True, header=True)


def write_csv(df, file_name, index_label=None, columns=None, column_labels=None, transpose=True):
    """
    Print write_csv

    Parameters
    ----------
    df: pandas.DataFrame or pandas.Series
        traced dataframe
    file_name: str
        output file name
    index_label: str
        index name
    columns: list
        columns to write
    transpose: bool
        whether to transpose dataframe (ignored for series)
    Returns
    -------
    Nothing
    """

    assert len(file_name) > 0

    if not file_name.endswith('.%s' % CSV_FILE_TYPE):
        file_name = '%s.%s' % (file_name, CSV_FILE_TYPE)

    file_path = config.trace_file_path(file_name)

    if os.path.isfile(file_path):
        logger.debug("write_csv file exists %s %s" % (type(df).__name__, file_name))

    if isinstance(df, pd.DataFrame):
        # logger.debug("dumping %s dataframe to %s" % (df.shape, file_name))
        write_df_csv(df, file_path, index_label, columns, column_labels, transpose=transpose)
    elif isinstance(df, pd.Series):
        # logger.debug("dumping %s element series to %s" % (df.shape[0], file_name))
        write_series_csv(df, file_path, index_label, columns, column_labels)
    elif isinstance(df, dict):
        df = pd.Series(data=df)
        # logger.debug("dumping %s element dict to %s" % (df.shape[0], file_name))
        write_series_csv(df, file_path, index_label, columns, column_labels)
    else:
        logger.error("write_csv object for file_name '%s' of unexpected type: %s" %
                     (file_name, type(df)))


def slice_ids(df, ids, column=None):
    """
    slice a dataframe to select only records with the specified ids

    Parameters
    ----------
    df: pandas.DataFrame
        traced dataframe
    ids: int or list of ints
        slice ids
    column: str
        column to slice (slice using index if None)

    Returns
    -------
    df: pandas.DataFrame
        sliced dataframe
    """

    if np.isscalar(ids):
        ids = [ids]

    try:
        if column is None:
            df = df[df.index.isin(ids)]
        else:
            df = df[df[column].isin(ids)]
    except KeyError:
        # this happens if specified slicer column is not in df
        # df = df[0:0]
        raise RuntimeError("slice_ids slicer column '%s' not in dataframe" % column)

    return df


def get_trace_target(df, slicer):
    """
    get target ids and column or index to identify target trace rows in df

    Parameters
    ----------
    df: pandas.DataFrame
        dataframe to slice
    slicer: str
        name of column or index to use for slicing

    Returns
    -------
    (target, column) tuple

    target : int or list of ints
        id or ids that identify tracer target rows
    column : str
        name of column to search for targets or None to search index
    """

    target_ids = None  # id or ids to slice by (e.g. hh_id or person_ids or tour_ids)
    column = None  # column name to slice on or None to slice on index

    # special do-not-slice code for dumping entire df
    if slicer == 'NONE':
        return target_ids, column

    if slicer is None:
        slicer = df.index.name

    if isinstance(df, pd.DataFrame):
        # always slice by household id if we can
        if 'household_id' in df.columns:
            slicer = 'household_id'
        if slicer in df.columns:
            column = slicer

    if column is None and df.index.name != slicer:
        raise RuntimeError("bad slicer '%s' for df with index '%s'" % (slicer, df.index.name))

    table_refs = inject.get_injectable('traceable_table_refs', {})

    if df.empty:
        target_ids = None
    elif slicer in table_refs:
        # maps 'person_id' to 'persons', etc
        table_name = table_refs[slicer]
        target_ids = inject.get_injectable('trace_%s' % table_name, [])
    elif slicer == 'TAZ':
        target_ids = inject.get_injectable('trace_od', [])

    return target_ids, column


def trace_targets(df, slicer=None):

    target_ids, column = get_trace_target(df, slicer)

    if target_ids is None:
        targets = None
    else:

        if column is None:
            targets = df.index.isin(target_ids)
        else:
            targets = df[column].isin(target_ids)

    return targets


def has_trace_targets(df, slicer=None):

    target_ids, column = get_trace_target(df, slicer)

    if target_ids is None:
        found = False
    else:

        if column is None:
            found = df.index.isin(target_ids).any()
        else:
            found = df[column].isin(target_ids).any()

    return found


def hh_id_for_chooser(id, choosers):
    """

    Parameters
    ----------
    id - scalar id (or list of ids) from chooser index
    choosers - pandas dataframe whose index contains ids

    Returns
    -------
        scalar household_id or series of household_ids
    """

    if choosers.index.name == 'household_id':
        hh_id = id
    elif 'household_id' in choosers.columns:
        hh_id = choosers.loc[id]['household_id']
    else:
        hh_id = None

    return hh_id


def dump_df(dump_switch, df, trace_label, fname):
    if dump_switch:
        trace_label = extend_trace_label(trace_label, 'DUMP.%s' % fname)
        trace_df(df, trace_label, index_label=df.index.name, slicer='NONE', transpose=False)


def trace_df(df, label, slicer=None, columns=None,
             index_label=None, column_labels=None, transpose=True, warn_if_empty=False):
    """
    Slice dataframe by traced household or person id dataframe and write to CSV

    Parameters
    ----------
    df: pandas.DataFrame
        traced dataframe
    label: str
        tracer name
    slicer: Object
        slicer for subsetting
    columns: list
        columns to write
    index_label: str
        index name
    column_labels: [str, str]
        labels for columns in csv
    transpose: boolean
        whether to transpose file for legibility
    warn_if_empty: boolean
        write warning if sliced df is empty

    Returns
    -------
    Nothing
    """

    target_ids, column = get_trace_target(df, slicer)

    if target_ids is not None:
        df = slice_ids(df, target_ids, column)

    if warn_if_empty and df.shape[0] == 0 and target_ids != []:
        column_name = column or slicer
        logger.warning("slice_canonically: no rows in %s with %s == %s"
                       % (label, column_name, target_ids))

    if df.shape[0] > 0:
        write_csv(df, file_name=label, index_label=(index_label or slicer), columns=columns,
                  column_labels=column_labels, transpose=transpose)


def interaction_trace_rows(interaction_df, choosers, sample_size=None):
    """
    Trace model design for interaction_simulate

    Parameters
    ----------
    interaction_df: pandas.DataFrame
        traced model_design dataframe
    choosers: pandas.DataFrame
        interaction_simulate choosers
        (needed to filter the model_design dataframe by traced hh or person id)
    sample_size int or None
        int for constant sample size, or None if choosers have different numbers of alternatives
    Returns
    -------
    trace_rows : numpy.ndarray
        array of booleans to flag which rows in interaction_df to trace

    trace_ids : tuple (str,  numpy.ndarray)
        column name and array of trace_ids mapping trace_rows to their target_id
        for use by trace_interaction_eval_results which needs to know target_id
        so it can create separate tables for each distinct target for readability
    """

    # slicer column name and id targets to use for chooser id added to model_design dataframe
    # currently we only ever slice by person_id, but that could change, so we check here...

    table_refs = inject.get_injectable('traceable_table_refs', {})

    if choosers.index.name == 'person_id' and inject.get_injectable('trace_persons', False):
        slicer_column_name = choosers.index.name
        targets = inject.get_injectable('trace_persons', [])
    elif 'household_id' in choosers.columns and inject.get_injectable('trace_hh_id', False):
        slicer_column_name = 'household_id'
        targets = inject.get_injectable('trace_hh_id', [])
    elif 'person_id' in choosers.columns and inject.get_injectable('trace_persons', False):
        slicer_column_name = 'person_id'
        targets = inject.get_injectable('trace_persons', [])
    else:
        print(choosers.columns)
        raise RuntimeError("interaction_trace_rows don't know how to slice index '%s'"
                           % choosers.index.name)

    if sample_size is None:
        # if sample size not constant, we count on either
        # slicer column being in itneraction_df
        # or index of interaction_df being same as choosers
        if slicer_column_name in interaction_df.columns:
            trace_rows = np.in1d(interaction_df[slicer_column_name], targets)
            trace_ids = interaction_df.loc[trace_rows, slicer_column_name].values
        else:
            assert interaction_df.index.name == choosers.index.name
            trace_rows = np.in1d(interaction_df.index, targets)
            trace_ids = interaction_df[trace_rows].index.values

    else:

        if slicer_column_name == choosers.index.name:
            trace_rows = np.in1d(choosers.index, targets)
            trace_ids = np.asanyarray(choosers[trace_rows].index)
        elif slicer_column_name == 'person_id':
            trace_rows = np.in1d(choosers['person_id'], targets)
            trace_ids = np.asanyarray(choosers[trace_rows].person_id)
        elif slicer_column_name == 'household_id':
            trace_rows = np.in1d(choosers['household_id'], targets)
            trace_ids = np.asanyarray(choosers[trace_rows].household_id)
        else:
            assert False

        # simply repeat if sample size is constant across choosers
        assert sample_size == len(interaction_df.index) / len(choosers.index)
        trace_rows = np.repeat(trace_rows, sample_size)
        trace_ids = np.repeat(trace_ids, sample_size)

    assert type(trace_rows) == np.ndarray
    assert type(trace_ids) == np.ndarray

    trace_ids = (slicer_column_name, trace_ids)

    return trace_rows, trace_ids


def trace_interaction_eval_results(trace_results, trace_ids, label):
    """
    Trace model design eval results for interaction_simulate

    Parameters
    ----------
    trace_results: pandas.DataFrame
        traced model_design dataframe
    trace_ids : tuple (str,  numpy.ndarray)
        column name and array of trace_ids from interaction_trace_rows()
        used to filter the trace_results dataframe by traced hh or person id
    label: str
        tracer name

    Returns
    -------
    Nothing
    """

    assert type(trace_ids[1]) == np.ndarray

    slicer_column_name = trace_ids[0]

    trace_results[slicer_column_name] = trace_ids[1]

    targets = np.unique(trace_ids[1])

    if len(trace_results.index) == 0:
        return

    # write out the raw dataframe
    file_path = config.trace_file_path('%s.raw.csv' % label)
    trace_results.to_csv(file_path, mode="a", index=True, header=True)

    # if there are multiple targets, we want them in separate tables for readability
    for target in targets:

        df_target = trace_results[trace_results[slicer_column_name] == target]

        # we want the transposed columns in predictable order
        df_target.sort_index(inplace=True)

        # # remove the slicer (person_id or hh_id) column?
        # del df_target[slicer_column_name]

        target_label = '%s.%s.%s' % (label, slicer_column_name, target)

        trace_df(df_target,
                 label=target_label,
                 slicer="NONE",
                 transpose=True,
                 column_labels=['expression', None],
                 warn_if_empty=False)


def no_results(trace_label):
    """
    standard no-op to write tracing when a model produces no results

    """
    logger.info("Skipping %s: no_results" % trace_label)
