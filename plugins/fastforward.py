#!/usr/bin/python3

import subprocess
import csv
from pathlib import Path

from adblib import print_codes

from core.config import ConfigSettings

##########################################################################
#
# Tracetool plugin for fastforwarding
#
##########################################################################


class tracetool(object):
    def __init__(self, adb):
        self.adb = adb
        self.config = ConfigSettings()
        self.plugin_name = 'fastforward'
        self.full_name = 'Fastforwarder plugin for retracers'

    def replay_start_fastforward(self, file, currentTool, from_frame, to_frame):  # special case
        """
        Makes a fastforward trace.

        Args:
            file (str): Path on remothe to trace file
            currentTool (obj): The current replayer tool plugin
            from_frame (int): Start fastforward from this frame
            to_frame (int): End fastforward at this frame. If None fastfordward will end at end of trace

        Returns:
            list: With paths to result files
        """
        # set up tracing of the replayer
        trace_name = Path(file).stem
        trace_base = Path(file).parent
        results = {}
        currentTool.trace_setup_device(currentTool.replayer['name'])

        if currentTool.plugin_name == 'gfxreconstruct':
            # Add/change some tracing parameters
            if to_frame is None:
                # Will make it run to the end as long as the trace does not contain
                # more than 999_999 frames
                to_frame = 999_999

            self.adb.setprop(
                'debug.gfxrecon.capture_frames',
                f'{from_frame}-{to_frame}')
            ff_name = f"{trace_name}"
            filename = f"{trace_base}/{ff_name}.gfxr"
            if len(filename) > 91:
                ff_name = "ff"
                print("[ INFO ] Capture file name too long. Removing trace name from filename.")
                filename = f"{trace_base}/{ff_name}.gfxr"
            # Needs to be less than 92 characters
            self.adb.setprop('debug.gfxrecon.capture_file', filename)
            output_file = f"{trace_base}/{ff_name}_frames_{from_frame}_through_{to_frame}.gfxr"

            # Set up parameters for the replayer
            cmd = [
                f"ANDROID_SERIAL={self.adb.device}",
                'python',
                str(currentTool.basepath / currentTool.dirname / currentTool.replayer['script']),
                'replay',
                '-m', 'rebind',
                str(file)
            ]

        elif currentTool.plugin_name == 'patrace':
            if to_frame:
                output_file = trace_base / f'{trace_name}_ff_{from_frame}_to_{to_frame}.pat'
            else:
                output_file = trace_base / f'{trace_name}_ff_{from_frame}_to_end.pat'

            cmd = [
                'am', 'start',
                '-n', f'{currentTool.replayer["name"]}/.Activities.FastforwardActivity',
                '--es', 'input', str(file),
                '--es', 'output', str(output_file),
                '--ei', 'targetFrame', from_frame
            ]

            if to_frame is not None:
                cmd.extend(['--ei', 'endFrame', to_frame])

        # Replay
        cmdstr = (" ").join([str(x) for x in cmd])
        print(f"[ INFO ] Running replay command: {cmdstr}")
        return cmd, output_file

    def generateHWC(self, ff_trace, source_trace, currentTool, from_frame, replayer=None, prev_results={}, extra_args=[]):
        """
        Generate hardware counters.

        Args:
            ff_trace (str): Path on remote to fastforward trace file
            source_trace (str): Path on remote to full source trace file
            currentTool (obj): The current replayer tool plugin.
            from_frame (int): Start frame of frame range
            extra_args (list): Additional replay args
            prev_results (dict): Previous results when fastforwarding multiple traces

        Returns:
            list: With paths to result files

        """
        results = {}

        if currentTool.plugin_name == 'gfxreconstruct':
            extra_args.extend(['--flush-inside-measurement-range', '--wait-before-present'])
            measurement_range_args = ['--measurement-frame-range', '1-10', '--quit-after-measurement-range']
        elif currentTool.plugin_name == 'patrace':
            extra_args.extend(['--ez', 'finishBeforeSwap', 'true'])
            measurement_range_args = ['--ei', 'frame_start', '1', '--ei', 'frame_end', '10']

        print(f"[ INFO ] Replaying FF trace to get HWC: {ff_trace}")
        results_ff_all = []
        for i in range(3):
            results_ff_hwc = replayer.replay(trace=ff_trace, screenshots=False, hwc=True, repeat=1, extra_args=measurement_range_args + extra_args)
            ff_hwc_path = results_ff_hwc.get('hwc_path', '')
            ff_hwc_path_local = f"{self.config.get_config()['Paths']['hwc_path']}/ff_hwc/{i}"
            self.adb.pull(ff_hwc_path, ff_hwc_path_local)
            ff_hwc_path_local = f"{ff_hwc_path_local}/{ff_hwc_path.split('/')[-1]}"
            results_ff_all.append(ff_hwc_path_local)
        ff_hwc_minimum = self.collate_hwc(results_ff_all)

        results_source_hwc = prev_results.get('results_source_hwc', {})
        source_hwc_path_local = f"{self.config.get_config()['Paths']['hwc_path']}/source_hwc"
        source_hwc_path = results_source_hwc.get('hwc_path', '')
        if not prev_results:
            print(f"[ INFO ] Replaying Source trace to get HWC: {ff_trace}")
            results_source_hwc = replayer.replay(trace=source_trace, screenshots=False, hwc=True, repeat=1, extra_args=extra_args)
            source_hwc_path = results_source_hwc.get('hwc_path', '')
            self.adb.pull(source_hwc_path, source_hwc_path_local)

        source_hwc_path_local = f"{source_hwc_path_local}/{source_hwc_path.split('/')[-1]}"
        print(f"[ INFO ] Starting HWC comparison")
        hwc_diffs = self.compare_hwc(ff_hwc_minimum, source_hwc_path_local, offset=from_frame)
        print(f"[ INFO ] HWC comparison done")

        results['ff_trace'] = Path(ff_trace)
        results['ff_hwc_diffs'] = hwc_diffs
        results['results_source_hwc'] = results_source_hwc

        return results

    def compare_hwc(self, results_ff, results_source, offset):
        """
        Hardware counter comparison
        Compares two CSVs cell-by-cell. Skips columns that are not in metrics. Diffs exceeding 10% will be displayed.

        Args:
            results_ff (file): CSV containing hwc from FF trace
            results_source (file): CSV containing hwc from source trace
            offset (int): CSV row offset

        Returns:
            dict: With HWC frame diff results
        """
        metrics = {'GPU active cycle': [-10.0, 10.0],
                   'Fragment active cycles': [-10.0, 10.0],
                   'Fragment jobs': [-10.0, 10.0],
                   'Non-fragment active cycles': [-10.0, 10.0],
                   'Non-fragment jobs': [-10.0, 10.0],
                   'Tiles': [-10.0, 10.0],
                   'Killed unchanged tiles': [-10.0, 10.0],
                   'Rasterized fine quads': [-10.0, 10.0],
                   'Non-fragment core tasks': [-10.0, 10.0],
                   'Arithmetic FMA pipe instructions': [-10.0, 10.0],
                   'Triangle primitives': [0.0, 0.0],
                   'Tiler active cycles': [-10.0, 10.0],
                   'Load/store unit full read issues': [-10.0, 10.0],
                   'Load/store unit partial read issues': [-10.0, 10.0],
                   'Load/store unit full write issues': [-10.0, 10.0],
                   'Load/store unit partial write issues': [-10.0, 10.0],
                   'Load/store unit atomic issues': [-10.0, 10.0],
                   'Output external read beats': [-10.0, 10.0],
                   'Output external write beats': [-10.0, 10.0],
                   'Ray tracing triangle batches tested': [-10.0, 10.0],
                   'Ray tracing box tests': [-10.0, 10.0],
                   'Ray tracing started rays': [0.0, 0.0],
                   'Ray tracing box tester issue cycles': [-10.0, 10.0],
                   'Ray tracing triangle tester issue cycles': [-10.0, 10.0],
                   'Ray tracing unit active cycles': [-10.0, 10.0]}

        diff_results = {"diffs": []}

        with open(results_ff, newline="") as f1, open(results_source, newline="") as f2:
            ff_hwc = csv.DictReader(f1)
            source_hwc = csv.DictReader(f2)

            # Check if headers match
            if ff_hwc.fieldnames != source_hwc.fieldnames:
                raise ValueError(f"Headers differ: {ff_hwc.fieldnames}  {source_hwc.fieldnames}")

            # Offset rows in the longer source HWC csv
            for _ in range(offset - 1):
                next(source_hwc, None)

            # Using frame number offset to align rows in ff_hwc and source_hwc
            row_num = offset
            for ff_row in ff_hwc:
                source_row = next(source_hwc, None)
                if source_row is None:
                    print("[ WARNING ] Source HWC file unexpectedly ran out of rows early.")
                    break

                for col in ff_hwc.fieldnames:
                    # Skip frames that are not selected frame
                    if row_num != offset + 1:
                        break
                    if col not in metrics:
                        continue
                    v1, v2 = ff_row[col], source_row[col]
                    if not v1 or not v2:
                        print(f"[ WARNING ] Missing value when comparing ff frame {row_num-offset} with source frame {row_num-1}, column '{col}': {v1}  {v2}")
                        continue
                    diff_value = float(v2) - float(v1)
                    if float(v2) != 0:
                        change_ratio = float(diff_value) / float(v2)
                    else:
                        if diff_value != 0:
                            change_ratio = 999.0 * (float(diff_value) / abs(diff_value))
                        else:
                            change_ratio = 0.0

                    change_percentage = change_ratio * 100.0
                    if not change_percentage >= metrics[col][0] and change_percentage <= metrics[col][1]:
                        # Frame numbers are 0-indexed
                        print(f"[ WARNING ] Diff above {metrics[col][1]}% or below {metrics[col][0]}% when comparing ff frame {row_num-offset} with source frame {row_num-1}, column '{col}': {v1}  {v2}")
                        print(f"[ INFO ] DIFF: {diff_value}\n DIFF RATIO: {change_ratio}\n DIFF PERCENTAGE: {change_percentage}")
                        frame_diffs = {'source_frame': row_num, 'ff_frame': row_num - offset,
                                       'metric': col, 'source_value': v2, 'ff_value': v1,
                                       'diff_value': diff_value, 'diff_ratio': change_ratio, 'diff_percentage': change_percentage,
                                       'max_diff_percentage': metrics[col][1], 'min_diff_percentage': metrics[col][0]}
                        diff_results['diffs'].append(frame_diffs)

                row_num += 1

        return diff_results

    def collate_hwc(self, results_all):
        """
        Collate HWC
        Combines all HWC outputs from FF trace and only returns minimum value.

        Args:
            results_all (list): List containing paths to HWC outputs from FF trace
        """
        output = f"tmp/hwc/ff_hwc_minimum.csv"

        with open(results_all[0], newline='') as f1, \
                open(results_all[1], newline='') as f2, \
                open(results_all[2], newline='') as f3, \
                open(output, 'w', newline='') as fout:

            reader1 = csv.reader(f1)
            reader2 = csv.reader(f2)
            reader3 = csv.reader(f3)
            writer = csv.writer(fout)

            # Check that header rows are matching
            header1 = next(reader1)
            header2 = next(reader2)
            header3 = next(reader3)
            if header1 != header2 or header1 != header3:
                raise ValueError("Headers do not match!")
            writer.writerow(header1)

            for row1, row2, row3 in zip(reader1, reader2, reader3):
                min_row = [min(float(c1), float(c2), float(c3)) for c1, c2, c3 in zip(row1, row2, row3)]
                writer.writerow(min_row)

        print(f"Minimum values saved to {output}")
        return output
