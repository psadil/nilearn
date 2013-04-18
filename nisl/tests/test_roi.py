"""
Test for roi module.
"""
# License: simplified BSD

import numpy as np
import scipy.signal as spsignal
from .. import roi
from .. import masking
from nose.tools import assert_raises


def generate_timeseries(n_instants, n_features,
                        randgen=None):
    """Generate some random timeseries. """
    if randgen is None:
        randgen = np.random.RandomState(0)
    return randgen.randn(n_instants, n_features)


def generate_regions_ts(n_features, n_regions,
                        overlap=0,
                        randgen=None,
                        window="boxcar"):
    """Generate some regions.

    Parameters
    ==========
    overlap (int)
        Number of overlapping voxels between two regions (more or less)
    window (str)
        Name of a window in scipy.signal. e.g. "hamming".

    Returns
    =======
    regions (numpy.ndarray)
        timeseries representing regions.
        shape (n_features, n_regions)
    """

    if randgen is None:
        randgen = np.random.RandomState(0)
    if window is None:
        window = "boxcar"

    assert(n_features > n_regions)

    # Compute region boundaries indices.
    # Start at 1 to avoid getting an empty region
    boundaries = np.zeros(n_regions + 1)
    boundaries[-1] = n_features
    boundaries[1:-1] = randgen.permutation(range(1, n_features)
                                           )[:n_regions - 1]
    boundaries.sort()

    regions = np.zeros((n_features, n_regions))
    overlap_end = int((overlap + 1) / 2)
    overlap_start = int(overlap / 2)
    for n in xrange(len(boundaries) - 1):
        start = max(0, boundaries[n] - overlap_start)
        end = min(n_features, boundaries[n + 1] + overlap_end)
        win = spsignal.get_window(window, end - start)
        win /= win.mean()  # unity mean
        regions[start:end, n] = win

    ## # Check that no regions overlap
    ## np.testing.assert_array_less((regions > 0).sum(axis=-1) - 0.1,
    ##                              np.ones(regions.shape[0]))
    return regions


def generate_labeled_regions(shape, n_regions, randgen=None):
    """Generate a 3D volume with labeled regions"""
    n_voxels = shape[0] * shape[1] * shape[2]
    regions = generate_regions_ts(n_voxels, n_regions, randgen=randgen)
    # replace weights with labels
    for n, col in enumerate(regions.T):
        col[col > 0] = n + 1
    return masking.unmask(regions.sum(axis=1), np.ones(shape, dtype=np.bool))


def test_apply_roi():
    n_instants = 101
    n_voxels = 54
    n_regions = 11

    # First generate signal based on _non-overlapping_ regions, then do
    # the reverse. Check that the starting signals are recovered.
    ts_roi = generate_timeseries(n_instants, n_regions)
    regions_nonflat = generate_regions_ts(n_voxels, n_regions,
                                          window="hamming")
    regions = np.where(regions_nonflat > 0, 1, 0)
    timeseries = roi.unapply_roi(ts_roi, regions)
    recovered = roi.apply_roi(timeseries, regions)

    np.testing.assert_almost_equal(ts_roi, recovered, decimal=14)

    # Extract one timeseries from each region, they must be identical
    # to ROI timeseries.
    indices = regions.argmax(axis=0)
    recovered2 = roi.apply_roi(timeseries, regions_nonflat,
                               normalize_regions=True)
    region_signals = timeseries.T[indices].T
    np.testing.assert_almost_equal(recovered2, region_signals)


def test_regions_convert():
    """Test of conversion functions between different regions structures.
    Function tested:
    regions_labels_to_array
    regions_array_to_labels
    """

    shape = (4, 5, 6)
    n_regions = 11

    ## labels <-> 4D array
    regions_labels = generate_labeled_regions(shape, n_regions)

    # FIXME: test dtype argument
    # FIXME: test labels argument
    regions_4D, labels = roi.regions_labels_to_array(regions_labels)
    assert(regions_4D.shape == shape + (n_regions,))
    regions_labels_recovered = roi.regions_array_to_labels(regions_4D)

    np.testing.assert_almost_equal(regions_labels_recovered, regions_labels)

    ## 4D array <-> list of 3D arrays
    regions_list = roi.regions_array_to_list(regions_4D, copy=False)
    assert (len(regions_list) == regions_4D.shape[-1])
    for n in xrange(regions_4D.shape[-1]):
        np.testing.assert_almost_equal(regions_list[n], regions_4D[..., n])

    regions_4D_recovered = roi.regions_list_to_array(regions_list)
    np.testing.assert_almost_equal(regions_4D_recovered, regions_4D)
    # check that arrays in list are views (modifies arrays)
    for n in xrange(regions_4D.shape[-1]):
        regions_list[n][0, 0, 0] = False
        regions_4D[0, 0, 0, n] = True
        assert(regions_list[n][0, 0, 0] == regions_4D[0, 0, 0, n])

    # Assert that data have been copied
    regions_list = roi.regions_array_to_list(regions_4D, copy=True)
    for n in xrange(regions_4D.shape[-1]):
        regions_list[n][0, 0, 0] = False
        regions_4D[0, 0, 0, n] = True
        assert(regions_list[n][0, 0, 0] != regions_4D[0, 0, 0, n])

    # Use "labels" argument
    regions_labels += 3
    regions_4D, labels = roi.regions_labels_to_array(regions_labels)
    regions_labels_recovered = roi.regions_array_to_labels(regions_4D,
                                                           labels=labels)
    np.testing.assert_almost_equal(regions_labels_recovered, regions_labels)
    regions_labels_recovered = roi.regions_array_to_labels(regions_4D,
                                                 labels=np.asarray(labels))
    np.testing.assert_almost_equal(regions_labels_recovered, regions_labels)

    assert_raises(ValueError, roi.regions_array_to_labels,
                  regions_4D, labels=[])

    ## list of 3D arrays <-> labels
    # First case
    regions_labels = generate_labeled_regions(shape, n_regions)
    regions_list, labels = roi.regions_labels_to_list(regions_labels,
                                              background_label=1)
    assert(len(labels) == len(regions_list))
    assert(len(regions_list) == n_regions - 1)
    assert(regions_list[0].shape == regions_labels.shape)
    assert(regions_list[0].dtype == np.bool)
    regions_labels_recovered = roi.regions_list_to_labels(regions_list,
                                                          labels=labels,
                                                          background_label=1)
    np.testing.assert_almost_equal(regions_labels, regions_labels_recovered)

    # same with different dtype
    regions_list, labels = roi.regions_labels_to_list(regions_labels,
                                                      background_label=1,
                                                      dtype=np.float)
    assert(regions_list[0].dtype == np.float)
    regions_labels_recovered = roi.regions_list_to_labels(regions_list,
                                                          labels=labels,
                                                          background_label=1)
    np.testing.assert_almost_equal(regions_labels, regions_labels_recovered)

    # second case: no background
    regions_labels = generate_labeled_regions(shape, n_regions)
    regions_list, labels = roi.regions_labels_to_list(regions_labels,
                                                      background_label=None)
    assert(len(labels) == len(regions_list))
    assert(len(regions_list) == n_regions)
    assert(regions_list[0].shape == regions_labels.shape)

    regions_labels_recovered = roi.regions_list_to_labels(regions_list)
    np.testing.assert_almost_equal(regions_labels, regions_labels_recovered)

    ## check conversion consistency (labels -> 4D -> list -> labels)
    # loop one way
    regions_labels = generate_labeled_regions(shape, n_regions)
    regions_array, _ = roi.regions_labels_to_array(regions_labels)
    regions_list = roi.regions_array_to_list(regions_array)
    regions_labels_recovered = roi.regions_list_to_labels(regions_list)

    np.testing.assert_almost_equal(regions_labels_recovered, regions_labels)

    # loop the other way
    regions_list, _ = roi.regions_labels_to_list(regions_labels,
                                                 background_label=None)
    regions_array = roi.regions_list_to_array(regions_list)
    regions_labels_recovered = roi.regions_array_to_labels(regions_array)

    np.testing.assert_almost_equal(regions_labels_recovered, regions_labels)


def test_regions_are_overlapping():
    """Test of regions_are_overlapping()"""

    shape = (4, 5, 6)
    n_voxels = shape[0] * shape[1] * shape[2]
    n_regions = 11

    # masked array of labels
    regions = generate_regions_ts(n_voxels, n_regions,
                                  window="hamming")
    assert(not roi.regions_are_overlapping(regions))

    regions[0, :2] = 1  # make regions overlap
    assert(roi.regions_are_overlapping(regions))

    # 3D volume with labels. No possible overlap.
    regions_labels = generate_labeled_regions(shape, n_regions)
    assert(not roi.regions_are_overlapping(regions_labels))

    # 4D volume, with weights
    regions_4D, labels = roi.regions_labels_to_array(regions_labels)
    assert(not roi.regions_are_overlapping(regions_4D))

    regions_4D[0, 0, 0, :2] = 1  # Make regions overlap
    assert(roi.regions_are_overlapping(regions_4D))

    # List of arrays
    regions_list = roi.regions_array_to_list(regions_4D)
    assert(roi.regions_are_overlapping(regions_list))

    regions_4D, labels = roi.regions_labels_to_array(regions_labels)
    regions_list = roi.regions_array_to_list(regions_4D)
    assert(not roi.regions_are_overlapping(regions_list))

    # Bad input
    assert_raises(TypeError, roi.regions_are_overlapping, None)
    assert_raises(TypeError, roi.regions_are_overlapping,
                  np.zeros((2, 2, 2, 2, 2)))



    # TODO:
    # - check with / without labels
    # - check overlapping / not overlapping
    # - check with / without holes
    # - check length consistency assertion
