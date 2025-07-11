#!/usr/bin/python3

"""
Simplified implementation of the standard arm frame selection method.
Is deterministic for the same input data.

Keep this script simple, dont import any scipy modules or other complex
libs that are not part of the standart python distributions on linux.
"""

import argparse
import json
import os
import math
from copy import deepcopy
import random

import pandas

from adblib import print_codes


GPU_ACTIVE_SAMPLE_INDEX = 0
LARGE_NUMBER = 99999999999999999999999999999


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("-i", "--input-csv", dest="input_csv", type=str)

    return parser.parse_args()

def process_hwc(csv_file):
    data = pandas.read_csv(csv_file)
    data.fillna(0, inplace=True)
    if "GPU active cycles" not in data.columns:
        print(f"[ WARNING ] GPU active counter is missing. Setting counters to 0.")
        data["GPU active cycles"] = 0

    # Just sum everything for now, figure out what to include properly later
    data["Bytes/Cy"] = (
            data["Tile unit write bytes"] +
            data["Load/store unit write bytes"] +
            data["Load/store unit read bytes from L2 cache"] +
            data["Texture unit read bytes from L2 cache"] +
            data["Front-end unit read bytes from L2 cache"]
    )
    data["Bytes/Cy"] /= data["GPU active cycles"]

    data["Prim/Cy"] = (
            data["Point primitives"] +
            data["Line primitives"] +
            data["Triangle primitives"]
    )

    data["Prim/Cy"] /= data["GPU active cycles"]
    data = data.rename(columns={
        "GPU active cycles": "GPU Active",
        "Execution core utilization": "EE Util",
        "Load/store unit utilization": "LSC Util",
        "Varying unit utilization": "Var Util",
        "Texture unit utilization": "Tex Util",
    })

    # GPU active must be at index 0 always.
    frame_selection_columns = ["GPU Active", "Bytes/Cy", "Prim/Cy", "EE Util", "LSC Util", "Var Util", "Tex Util"]

    data_filtered = data[frame_selection_columns]

    return data_filtered.values.tolist()

def normalize_samples(samples):
    sample_size = len(samples[0])
    num_samples = len(samples)

    sample_maxes = [-LARGE_NUMBER for _ in range(sample_size)]
    sample_mins = [LARGE_NUMBER for _ in range(sample_size)]

    for sample in samples:
        for index, value in enumerate(sample):
            if sample_maxes[index] < value:
                sample_maxes[index] = value
            if sample_mins[index] > value:
                sample_mins[index] = value

    normalized_samples = []
    for sample in samples:
        normalized_sample = [0] * sample_size
        for sindex, value in enumerate(sample):
            svalue_range = sample_maxes[sindex] - sample_mins[sindex]
            if svalue_range > 0.0:
                normalized_sample[sindex] = (sample[sindex] - sample_mins[sindex]) / svalue_range

        normalized_samples.append(normalized_sample)

    return normalized_samples


# Main entry point
def select_frames(per_frame_hwc_data, frame_range_start=0, frame_range_end=LARGE_NUMBER, number_of_frames=1):
    frame_vector_samples = process_hwc(per_frame_hwc_data)

    if not len(frame_vector_samples):
        print(f"[ {print_codes.ERROR}ERROR{print_codes.END_CODE} ] Input sample CSV is empty, cant select any frames.")
        return None

    num_frames = len(frame_vector_samples)

    print(f"[ INFO ] Running frame selection on dataset containing {num_frames} frames")

    if frame_range_start > num_frames:
        raise Exception(f"Selected start frame {frame_range_start} is bigger than the total number of frames {num_frames}")

    if frame_range_end > num_frames:
        frame_range_end = num_frames

    if frame_range_start >= frame_range_end:
        raise Exception("Frame range start was greater than or equal to frame range end.")

    frame_vector_samples = frame_vector_samples[frame_range_start: frame_range_end]

    print(f"[ INFO ] Number of frames in frame range: {len(frame_vector_samples)}")

    normalized_samples = normalize_samples(frame_vector_samples)

    selected_frames = pick_frames(number_of_frames, normalized_samples, frame_vector_samples, frame_range_start)

    return selected_frames


def calc_sum(v1, v2):
    return [x + y for x, y in zip(v1, v2)]


def calc_distance(v1, v2):
    summed = 0
    for val1, val2 in zip(v1, v2):
        diff = val2 - val1
        summed += diff * diff

    return math.sqrt(summed)


def run_k_means(initial_cluster_centers, samples, num_runs=1, tolerance=0.001, max_iterations=1000):
    sample_clusters = [-1 for _ in range(len(samples))]
    cluster_centers = deepcopy(initial_cluster_centers)

    iteration = 0
    done = False
    while not done:
        print(f"[ INFO ] Running KMeans iteration {iteration} with {len(cluster_centers)} clusters.")

        done = True

        for sample_index, sample in enumerate(samples):
            min_dist = LARGE_NUMBER

            for cluster_index, cluster in enumerate(cluster_centers):
                dist = calc_distance(sample, cluster)
                if dist < min_dist:
                    min_dist = dist
                    sample_clusters[sample_index] = cluster_index

        cluster_dists = {}
        for sample_index, sample_cluster in enumerate(sample_clusters):
            if sample_cluster not in cluster_dists:
                cluster_dists[sample_cluster] = {
                    "sample_count": 0,
                    "sample_sum": [0.0] * len(samples[0])
                }

            cluster_dists[sample_cluster]["sample_count"] += 1.0
            cluster_dists[sample_cluster]["sample_sum"] = calc_sum(cluster_dists[sample_cluster]["sample_sum"], samples[sample_index])

        for cluster_index, cluster_data in cluster_dists.items():
            new_cluster = [float(val) / cluster_data["sample_count"] for val in cluster_data["sample_sum"]]
            cluster_improvement = calc_distance(new_cluster, cluster_centers[cluster_index])

            if cluster_improvement > tolerance:
                done = False
                cluster_centers[cluster_index] = new_cluster

        iteration += 1

        if iteration > max_iterations:
            print(f"[ {print_codes.WARNING}WARNING{print_codes.END_CODE} ] KMeans reached the maximum number of iterations which was {max_iterations}, selected frames may not be great!")
            done = True

    print(f"[ INFO ] Finished KMeans after {iteration} iterations.")

    return sample_clusters, cluster_centers


def pick_frames(num_frames, samples, raw_samples, frame_range_start):
    # samples = samples[0:3]
    # raw_samples = raw_samples[0:3]
    num_clusters = num_frames
    sample_size = len(samples[0])
    num_samples = len(samples)

    cluster_centers = []

    step_size = math.floor(num_samples / 3.0)
    step_init = math.floor(step_size / 2.0)

    if step_size == 0:
        for _ in range(num_clusters):
            cluster_centers.append([random.random() for _ in range(sample_size)])
    else:
        # Spread the initial centers across the frame samples with even distance.
        # This leads to much better + faster convergence since neighboring frames tend to be similar
        print(f"[ INFO ] Initializing clusters using step size {step_size} and initial offset {step_init}")
        for cluster_index in range(num_clusters):
            cluster_centers.append(deepcopy(samples[step_init + cluster_index * step_size]))

    sample_cluster_indices, cluster_centers = run_k_means(cluster_centers, samples)

    cluster_best_sample_meta = {}

    for sample_index, sample_cluster_index in enumerate(sample_cluster_indices):
        if sample_cluster_index not in cluster_best_sample_meta:
            cluster_best_sample_meta[sample_cluster_index] = {
                "min_dist": LARGE_NUMBER,
                "best_sample_index": -1,
                "gpu_active_sum": 0,
                "num_frames_in_cluster": 0,
                "inv_gpu_active_sum": 0
            }

        gpu_active_sample_data = raw_samples[sample_index][GPU_ACTIVE_SAMPLE_INDEX]
        if gpu_active_sample_data == 0:
            continue

        cluster_center = cluster_centers[sample_cluster_index]

        dist_to_center = calc_distance(cluster_center, samples[sample_index])

        if dist_to_center < cluster_best_sample_meta[sample_cluster_index]["min_dist"]:
            cluster_best_sample_meta[sample_cluster_index]["min_dist"] = dist_to_center
            cluster_best_sample_meta[sample_cluster_index]["best_sample_index"] = sample_index

        # Compute weight related data
        cluster_best_sample_meta[sample_cluster_index]["num_frames_in_cluster"] += 1
        cluster_best_sample_meta[sample_cluster_index]["gpu_active_sum"] += gpu_active_sample_data
        cluster_best_sample_meta[sample_cluster_index]["inv_gpu_active_sum"] += 1.0 / gpu_active_sample_data

    for cluster_index, cluster_data in cluster_best_sample_meta.items():
        # Default weight is just the proportion of frames in this cluster
        raw_weight = cluster_data["num_frames_in_cluster"] / num_samples
        if cluster_data["num_frames_in_cluster"] == 0:
            continue
        real_mean = cluster_data["gpu_active_sum"] / cluster_data["num_frames_in_cluster"]
        stereotype_mean = raw_samples[cluster_data["best_sample_index"]][GPU_ACTIVE_SAMPLE_INDEX]
        # Corrected mean takes into account how far the selected frame is from the cluster mean
        cluster_data["fixed_rate_weight"] = (real_mean / stereotype_mean) * raw_weight

        real_mean = cluster_data["inv_gpu_active_sum"] / cluster_data["num_frames_in_cluster"]
        cluster_data["fixed_time_weight"] = real_mean * stereotype_mean * raw_weight

    return [
        {
            "frame": cluster_data["best_sample_index"] + frame_range_start,
            "fixed_rate_weight": cluster_data["fixed_rate_weight"],
            "fixed_time_weight": cluster_data["fixed_time_weight"],
            "num_frames_in_cluster": cluster_data["num_frames_in_cluster"]
        } for cluster_data in cluster_best_sample_meta.values() if cluster_data["best_sample_index"] != -1
    ]


if __name__ == "__main__":
    ARGS = parse_args()

    selected_frames_single, selected_frames_triple = select_frames(ARGS.input_csv)

    print(f"[ INFO ] Successfully ran frame selection, selected frames: ")
    print(json.dumps(selected_frames_single, indent=2))
    print("\n\n")
    print(json.dumps(selected_frames_triple, indent=2))
