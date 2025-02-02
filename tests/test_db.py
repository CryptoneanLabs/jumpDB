import os

from jumpDB import DB, make_new_segment
import pytest


def test_simple_db_search():
    db = DB(max_inmemory_size=10, persist_segments=False)
    db["foo"] = "bar"
    assert db["foo"] == "bar"


def test_deletion():
    db = DB(max_inmemory_size=10, persist_segments=False)
    db["foo"] = "bar"
    del db["foo"]
    with pytest.raises(Exception):
        _ = db["foo"]


def test_db_search_with_exceeding_capacity():
    db = DB(max_inmemory_size=2, persist_segments=False)
    db["k1"] = "v1"
    db["k2"] = "v2"
    db["k3"] = "v3"
    assert db["k1"] == "v1"
    assert db["k2"] == "v2"
    assert db["k3"] == "v3"


def test_db_search_with_multiple_segments():
    db = DB(max_inmemory_size=2,
            segment_size=2,
            sparse_offset=5,
            persist_segments=False)

    # all unique k-v pairs
    kv_pairs = [("k" + str(i), "v" + str(i)) for i in range(5)]
    for (k, v) in kv_pairs:
        db[k] = v

    # we'll have 2 segments, each containing 2 entries); the memtable will contain the last entry
    assert db.segment_count() == 2
    for (k, v) in kv_pairs:
        assert db[k] == v


def test_db_search_with_single_merged_segment():
    db = DB(max_inmemory_size=2,
            segment_size=2,
            sparse_offset=5,
            merge_threshold=2,
            persist_segments=False)
    kv_pairs = [("k1", "v1"), ("k2", "v2"), ("k1", "v1_1"), ("k2", "v2_2"),
                ("k3", "v3")]
    for (k, v) in kv_pairs:
        db[k] = v
    assert db.segment_count() == 1
    assert db["k1"] == "v1_1"
    assert db["k2"] == "v2_2"


def test_db_search_for_for_deleted_key():
    db = DB(max_inmemory_size=2, segment_size=2, persist_segments=False)
    db["k1"] = "v1"
    del db["k1"]
    db["k2"] = "v2"
    with pytest.raises(Exception):
        _ = db["k1"]


def test_db_contains_key():
    db = DB(max_inmemory_size=2, segment_size=2, persist_segments=False)
    db["k1"] = "v1"
    db["k2"] = "v2"
    db["k3"] = "v3"
    del db["k2"]
    assert "k1" in db
    assert "k2" not in db


def test_key_eviction_after_writing_to_sst():
    db = DB(max_inmemory_size=2, segment_size=2, persist_segments=False)
    db["k1"] = "v1"
    db["k2"] = "v2"
    db["k3"] = "k3"
    del db["k1"]
    db["k4"] = "v4"
    db["k5"] = "v5"
    assert "k1" not in db


def test_db_deletion_on_nonexistent_key():
    db = DB(max_inmemory_size=2, segment_size=2, persist_segments=False)
    with pytest.raises(Exception):
        _ = db["k1"]


def test_db_segment_loading():
    segment = make_new_segment(persist=True, base_path="sst_data")
    segment_entry = ("k1", "v1")
    with segment.open("w"):
        segment.add_entry(segment_entry)
    try:
        current_test_path = os.path.abspath(
            os.path.join(os.getcwd(), "sst_data"))
        db = DB(path=current_test_path)
        assert db.segment_count() == 1
        assert db["k1"] == "v1"

    finally:
        os.remove(segment.path)


def test_merging_with_n_segments():
    kv_pairs = [("k1", "v1"), ("k2", "v2"), ("k3", "v3"), ("k4", "k4"),
                ("k5", "v5")]
    db = DB(max_inmemory_size=1,
            segment_size=1,
            merge_threshold=4,
            persist_segments=False)
    for (k, v) in kv_pairs:
        db[k] = v
    assert db.segment_count() == 4
    for (k, v) in kv_pairs:
        assert db[k] == v


def test_internal_segment_ordering():
    segment_1 = make_new_segment(persist=True, base_path="sst_data")
    segment_1_entry = ("k1", "v1")
    segment_2 = make_new_segment(persist=True, base_path="sst_data")
    segment_2_entry = ("k2", "v2")
    segment_3 = make_new_segment(persist=True, base_path="sst_data")
    segment_3_entry = ("k2", "v2_2")
    with segment_1.open("w"), segment_2.open("w"), segment_3.open("w"):
        segment_1.add_entry(segment_1_entry)
        segment_2.add_entry(segment_2_entry)
        segment_3.add_entry(segment_3_entry)
    try:
        current_test_path = os.path.abspath(
            os.path.join(os.getcwd(), "sst_data"))
        db = DB(path=current_test_path)
        assert db.segment_count() == 3
        assert db["k1"] == "v1"
        assert db["k2"] == "v2_2"

    finally:
        os.remove(segment_1.path)
        os.remove(segment_2.path)
        os.remove(segment_3.path)


def test_worst_case_get():
    """
    In this test, we try to find the value corresponding to "k1_1"

    With the given db parameters, the sparse index will  have only one entry: "k1" -> segment_2
    Thus, we now have to look into all all segments to find correct entry

    :return:
    """
    segment_1 = make_new_segment(persist=True, base_path="sst_data")
    segment_1_entries = [("k1", "v1"), ("k1_1", "v_1")]
    segment_2 = make_new_segment(persist=True, base_path="sst_data")
    segment_2_entries = [("k1", "v1")]
    with segment_1.open("w"), segment_2.open("w"):
        for e in segment_1_entries:
            segment_1.add_entry(e)
        for e in segment_2_entries:
            segment_2.add_entry(e)
    try:
        current_test_path = os.path.abspath(
            os.path.join(os.getcwd(), "sst_data"))
        db = DB(path=current_test_path, sparse_offset=2)
        assert db.segment_count() == 2
        assert db["k1_1"] == "v_1"
    finally:
        os.remove(segment_1.path)
        os.remove(segment_2.path)


def test_db_for_large_dataset():
    db = DB(segment_size=2,
            merge_threshold=5,
            max_inmemory_size=10,
            persist_segments=False)
    kv_pairs = [("k" + str(i), "v" + str(i)) for i in range(50)]
    for (k, v) in kv_pairs:
        db[k] = v
    for (k, v) in kv_pairs[25:]:
        del db[k]
    for (k, v) in kv_pairs[:25]:
        assert db[k] == v
    for (k, v) in kv_pairs[25:]:
        assert k not in db

def test_db_for_explicit_flushing_to_disk():
    """
    write segment to disk even if below segment_size
    read data from disk
    """
    import shutil

    segment_1 = make_new_segment(persist=True, base_path="sst_data")
    segment_1_entries = [("k_01", "v_01"), ("k_02", "v_02")]
    with segment_1.open("w"):
        for e in segment_1_entries:
            segment_1.add_entry(e)
    try:
        current_test_path = os.path.abspath(
            os.path.join(os.getcwd(), "sst_data"))
        
        db = DB(path=current_test_path, segment_size=3)
        assert db['k_01'] == "v_01"
        db.flush()
        
        # read last data
        db2 = DB(path=current_test_path, segment_size=5)
        assert db2['k_02'] == "v_02"
    finally:
        # os.remove(segment_1.path)
        filelist = [ f for f in os.listdir('sst_data') if f.endswith(".dat") ]
        for f in filelist:
            os.remove(os.path.join('sst_data', f))

def test_db_for_very_large_datasets_to_disk():
    try:
        my_range = 100000
        db = DB(persist_segments=True, 
                segment_size=10000,
                max_inmemory_size=30000,
                sparse_offset=1000,
                path="sst_data2")
        kv_pairs = [("k" + str(i), "v" + str(i)) for i in range(my_range)]
        for (k, v) in kv_pairs:
            db[k] = v
        db.flush()
        assert db['k8888'] == "v8888"
        assert len(db) == my_range
    finally:
        print('done!')

def test_db_for_very_large_datasets_retrieval():
    try:
        my_range = 100000
        db = DB(persist_segments=True, 
                segment_size=10000,
                max_inmemory_size=30000,
                sparse_offset=1000,
                path="sst_data2")
        assert db['k8888'] == "v8888"
        assert len(db) == my_range
    finally:
        print('done!')
        filelist = [ f for f in os.listdir('sst_data2') if f.endswith(".dat") ]
        for f in filelist:
            os.remove(os.path.join('sst_data2', f))

def test_db_for_very_large_keys_and_datasets():
    import hashlib

    try:
        my_range = 10000
        db = DB(persist_segments=True, 
                segment_size=10000,
                max_inmemory_size=30000,
                sparse_offset=1000,
                path="sst_data3")
        kv_pairs = [( (str(i).zfill(19)+'-'+hashlib.md5(str(i).zfill(19).encode()).hexdigest()), "v" + str(i)) for i in range(my_range)]
        for (k, v) in kv_pairs:
            db[k] = v
        db.flush()
        assert db['0000000000000004105-b6e25c122b548cbdd3b4f342dfcf6aad'] == "v4105"
        assert len(db) == my_range
    finally:
        print('done!')
        filelist = [ f for f in os.listdir('sst_data3') if f.endswith(".dat") ]
        for f in filelist:
            os.remove(os.path.join('sst_data3', f))

def test_db_for_double_flush():
    import hashlib

    try:
        my_range = 10000
        db = DB(persist_segments=True, 
                segment_size=10000,
                max_inmemory_size=30000,
                sparse_offset=1000,
                path="sst_data3")
        db['0000000000000000001-b6e25c122b548cbdd3b4f342dfcf6aad'] = "v1"
        db.flush()
        db.flush()
        assert db['0000000000000000001-b6e25c122b548cbdd3b4f342dfcf6aad'] == "v1"
        assert len(db) == 1
    finally:
        print('done!')
        
    