from gc import collect
from os import listdir, path, makedirs, _exit
from time import sleep
from json import loads as load_bytes, dumps as dump_bytes
from mido import MidiFile, tick2second
from pynbt import TAG_Int, TAG_String, TAG_Compound, TAG_Short, NBTFile
from serial import Serial
from shutil import rmtree, move, make_archive
from pickle import loads, dumps
from random import randint
from hashlib import md5
from requests import get
from threading import Thread
from traceback import format_exc
from subprocess import Popen
from serial.serialutil import PARITY_EVEN
import serial.tools.list_ports
try:
    from flask import Flask, request, send_from_directory, jsonify
    from werkzeug.utils import secure_filename
    from flask_cors import CORS
except Exception:
    Flask = None
    CORS = None

def asset_load():
    """加载配置文件和资源"""
    try:
        if path.exists("Cache/Updater"):
            n = 0
            while n <= 16:
                try:
                    if path.isdir("Updater"):
                        rmtree("Updater")
                    break
                except Exception:
                    n += 1
            move("Cache/Updater", "Updater")
            rmtree("Cache")
        
        with open("Asset/text/setting.json", "rb") as io:
            asset_list["setting"] = load_bytes(io.read())
        asset_list["fps"] = asset_list["setting"]["setting"]["fps"]
        state[3][0] = int(asset_list["setting"]["setting"]["auto_gain"])
        state[3][2] = int(asset_list["setting"]["setting"]["speed"])
        state[3][3] = bool(asset_list["setting"]["setting"]["skip"])
        state[3][4] = bool(asset_list["setting"]["setting"]["enable_percussion"])
        state[3][5] = int(asset_list["setting"]["setting"]["mode"])
        state[3][6] = bool(asset_list["setting"]["setting"]["append_number"])
        state[3][7] = int(asset_list["setting"]["setting"]["file_type"])
        state[3][9] = int(asset_list["setting"]["setting"]["adjust_pitch"])
        state[3][10] = bool(asset_list["setting"]["setting"]["adjust_instrument"])
        log[0][1] = bool(asset_list["setting"]["setting"]["log_level"])
        
        with open("Asset/text/manifest.json", "rb") as io:
            asset_list["manifest"] = dumps(load_bytes(io.read()))
        asset_list["profile"] = []
        for n in listdir("Asset/profile"):
            with open("Asset/profile/" + n, "rb") as io:
                i = load_bytes(io.read())
                if "default" in i["description"]["feature"]:
                    asset_list["profile"].insert(0, (i["description"]["name"], i))
                else:
                    asset_list["profile"].append((i["description"]["name"], i))
        
        asset_list["structure_file"] = []
        for n in listdir("Asset/mcstructure"):
            if path.splitext(n)[1] == ".mcstructure":
                Thread(target=structure_load, args=[n]).start()
        
        print("✓ 配置文件加载完成")
    except Exception:
        save_log(1, "E:", format_exc())
    finally:
        collect()

def structure_load(n):
    with open("Asset/mcstructure/" + n, "rb") as structure:
        structure = NBTFile(structure, little_endian=True)
    i = (dumps(structure),
         str(structure["size"][0].value) +
         "*" + str(structure["size"][2].value) +
         "*" + str(structure["size"][1].value) +
         "  " + path.splitext(n)[0])
    if "推荐" in path.splitext(n)[0]:
        asset_list["structure_file"].insert(0, i)
    else:
        asset_list["structure_file"].append(i)
    del i
    del structure
    collect()

def convertor(midi_path, midi_name, cvt_setting, message_id=None):
    # message_id: external task id for API or UI. If not provided, use current global snapshot.
    if message_id is None:
        try:
            message_id = task_id
        except Exception:
            message_id = 0
    convertor_state = True
    message_list.append(["[--%] 正在加载 " + midi_name[0:-4], message_id])
    try:
        if cvt_setting[5] == 2:
            asset_list["setting"]["setting"]["id"] += 1
            play_id = str(asset_list["setting"]["setting"]["id"])
        else:
            play_id = "0.."
        if cvt_setting[7] == 2:
            output_name = "JE"
        else:
            output_name = "BE"
        output_name += uuid(8).upper()
        mid = MidiFile(midi_path + midi_name, clip=True)
        if cvt_setting[7] == 0:
            try:
                structure = loads(asset_list["structure_file"][cvt_setting[1]][0])
                total = structure["size"][0].value * structure["size"][1].value * structure["size"][2].value
                h = total - 1
            except Exception:
                convertor_state = "无可用模板"
                return
            manifest = {}
            behavior = []
        elif cvt_setting[7] == 1:
            structure = TAG_Compound({})
            manifest = loads(asset_list["manifest"])
            manifest["header"]["name"] = midi_name[0:-4]
            manifest["header"]["uuid"] = uuid(8) + "-" + uuid(4) + "-" + uuid(4) + "-" + uuid(4) + "-" + uuid(12)
            manifest["modules"][0]["uuid"] = uuid(8) + "-" + uuid(4) + "-" + uuid(4) + "-" + uuid(4) + "-" + uuid(12)
            behavior = [{"pack_id": manifest["header"]["uuid"], "version": manifest["header"]["version"]}]
            total = 0
            h = float("INF")
        elif cvt_setting[7] == 2:
            structure = TAG_Compound({})
            manifest = {}
            behavior = {"pack": {"pack_format": 1, "description": "§bby §dMIDI-MCSTRUCTURE"}}
            total = 0
            h = float("INF")
        else:
            structure = TAG_Compound({})
            manifest = {}
            behavior = []
            total = 0
            h = float("INF")
        num = 0
        for track in mid.tracks:
            for msg in track:
                if msg.type == "note_on" and msg.velocity != 0:
                    num += 1
        if cvt_setting[7] == 0:
            total += num * 2
        else:
            total = num * 3
        if len(message_list) == 0:
            message_list.append(["[0%] 正在转换 " + midi_name[0:-4], message_id])
        progress_bar(message_id, midi_name[0:-4], 0, 1)
        progress = 0
        offset_time = -1
        info_list = {}
        velocity_list = []
        pitch_list = [0, 0, 0, 0, 0, 0, 0, 0, 0]
        tempo_list = [(0, 500000), (float("INF"), 0)]
        for track in mid.tracks:
            source_time = 0
            for msg in track:
                source_time += msg.time
                if msg.type == "set_tempo":
                    for n, tmp in enumerate(tempo_list):
                        if tmp[0] > source_time:
                            tempo_list.insert(n, (source_time, msg.tempo))
                            break
                if msg.type == "control_change":
                    channel = msg.channel
                    if channel not in info_list:
                        info_list[channel] = {"volume": [(float("INF"), 1)]}
                    if msg.control == 7:
                        value = int(msg.value / 1.27) / 100
                        for n, vol in enumerate(info_list[channel]["volume"]):
                            if vol[0] >= source_time:
                                info_list[channel]["volume"].insert(n, (source_time, value))
                                break
                    elif msg.control == 121:
                        for n, vol in enumerate(info_list[channel]["volume"]):
                            if vol[0] >= source_time:
                                info_list[channel]["volume"].insert(n, (source_time, 1))
                                break
                if msg.type == "note_on":
                    note = msg.note - 21
                    channel = msg.channel
                    velocity = msg.velocity / 127
                    if velocity != 0:
                        if channel not in info_list:
                            info_list[channel] = {"volume": [(float("INF"), 1)]}
                        if cvt_setting[9] != 0 and channel != 9:
                            volume = 1
                            for vol in info_list[channel]["volume"]:
                                if vol[0] > source_time:
                                    break
                                else:
                                    volume = vol[1]
                            velocity *= volume
                            if 0 <= note <= 2:
                                pitch_list[0] += velocity
                            elif 3 <= note <= 14:
                                pitch_list[1] += velocity
                            elif 15 <= note <= 26:
                                pitch_list[2] += velocity
                            elif 27 <= note <= 38:
                                pitch_list[3] += velocity
                            elif 39 <= note <= 50:
                                pitch_list[4] += velocity
                            elif 51 <= note <= 62:
                                pitch_list[5] += velocity
                            elif 63 <= note <= 74:
                                pitch_list[6] += velocity
                            elif 75 <= note <= 86:
                                pitch_list[7] += velocity
                            elif note == 87:
                                pitch_list[8] += velocity
                        if cvt_setting[0] != 0:
                            velocity_list.append(velocity)
                        if cvt_setting[3]:
                            if (cvt_setting[4] or channel != 9) and (offset_time == -1 or source_time < offset_time):
                                offset_time = source_time
                        else:
                            offset_time = 0
                        progress += 1
                        progress_bar(message_id, "正在转换 " + midi_name[0:-4], progress, total)
        if offset_time:
            tick_time = 0
            for n in range(1, len(tempo_list)):
                if tempo_list[n][0] <= offset_time:
                    tick_time += tick2second(tempo_list[n][0] - tempo_list[n - 1][0], mid.ticks_per_beat, tempo_list[n - 1][1]) * 2000 / cvt_setting[2]
                else:
                    tick_time += tick2second(offset_time - tempo_list[n - 1][0], mid.ticks_per_beat, tempo_list[n - 1][1]) * 2000 / cvt_setting[2]
                    break
            offset_time = tick_time
        if cvt_setting[9] == 2:
            pitch_offset = [0, 0]
            for n, i in enumerate(pitch_list):
                if i >= pitch_offset[1]:
                    pitch_offset = [n, i]
            pitch_offset = (4 - pitch_offset[0]) * 12
        else:
            pitch_offset = 0
        total_vol = 1
        if cvt_setting[0] != 0:
            num = 0
            total_vol = 0
            velocity_list.sort()
            for n in velocity_list:
                total_vol += n
                num += 1
            total_vol /= num
            total_vol = int(cvt_setting[0] / total_vol) / 100
        if cvt_setting[5] == 1:
            append_num = 2
        elif cvt_setting[5] == 2:
            append_num = 2
        else:
            append_num = 0
        num = 0
        note_len = len(asset_list["profile"][cvt_setting[11]][1]["note_list"])
        time_list = []
        info_list = {}
        note_buffer = {}
        for track in mid.tracks:
            source_time = 0
            for msg in track:
                source_time += msg.time
                if msg.type == "set_tempo":
                    for n, tmp in enumerate(tempo_list):
                        if tmp[0] > source_time:
                            tempo_list.insert(n, (source_time, msg.tempo))
                            break
                if msg.type == "control_change":
                    channel = msg.channel
                    if channel not in info_list:
                        info_list[channel] = {"program": [(float("INF"), "")], "volume": [(float("INF"), 1)], "balance": [(float("INF"), "")]}
                    if msg.control == 7:
                        value = int(msg.value / 1.27) / 100
                        for n, vol in enumerate(info_list[channel]["volume"]):
                            if vol[0] > source_time:
                                info_list[channel]["volume"].insert(n, (source_time, value))
                                break
                    elif msg.control == 8 or msg.control == 10:
                        value = msg.value - 64
                        if value > 0:
                            value = value / -63
                        elif value < 0:
                            value = value / -64
                        for n, bal in enumerate(info_list[channel]["balance"]):
                            if bal[0] > source_time:
                                info_list[channel]["balance"].insert(n, (source_time, value))
                                break
                    elif msg.control == 121:
                        for n, bal in enumerate(info_list[channel]["balance"]):
                            if bal[0] > source_time:
                                info_list[channel]["balance"].insert(n, (source_time, 0))
                                break
                        for n, vol in enumerate(info_list[channel]["volume"]):
                            if vol[0] > source_time:
                                info_list[channel]["volume"].insert(n, (source_time, 1))
                                break
                if msg.type == "program_change":
                    program = str(msg.program)
                    channel = msg.channel
                    if channel not in info_list:
                        info_list[channel] = {"program": [(float("INF"), "")], "volume": [(float("INF"), 1)], "balance": [(float("INF"), "")]}
                    if channel != 9:
                        if cvt_setting[7] == 2:
                            if program in asset_list["profile"][cvt_setting[11]][1]["java"]["sound_list"]:
                                value = asset_list["profile"][cvt_setting[11]][1]["java"]["sound_list"][program]
                            else:
                                value = asset_list["profile"][cvt_setting[11]][1]["java"]["sound_list"]["undefined"]
                        else:
                            if program in asset_list["profile"][cvt_setting[11]][1]["bedrock"]["sound_list"]:
                                value = asset_list["profile"][cvt_setting[11]][1]["bedrock"]["sound_list"][program]
                            else:
                                value = asset_list["profile"][cvt_setting[11]][1]["bedrock"]["sound_list"]["undefined"]
                        for n, typ in enumerate(info_list[channel]["program"]):
                            if typ[0] > source_time:
                                info_list[channel]["program"].insert(n, (source_time, value))
                                break
                if msg.type == "note_on":
                    note = msg.note - 21
                    channel = msg.channel
                    velocity = msg.velocity
                    if velocity != 0:
                        if channel not in info_list:
                            info_list[channel] = {"program": [(float("INF"), "")], "volume": [(float("INF"), 1)], "balance": [(float("INF"), "")]}
                        volume = 1
                        for vol in info_list[channel]["volume"]:
                            if vol[0] > source_time:
                                break
                            else:
                                volume = vol[1]
                        balance = ""
                        for bal in info_list[channel]["balance"]:
                            if bal[0] > source_time:
                                break
                            else:
                                balance = round_45(bal[1], 2)
                        if channel == 9:
                            if cvt_setting[7] == 2:
                                if str(note + 21) in asset_list["profile"][cvt_setting[11]][1]["java"]["sound_list"]["percussion"]:
                                    program = asset_list["profile"][cvt_setting[11]][1]["java"]["sound_list"]["percussion"][str(note + 21)]
                                else:
                                    program = asset_list["profile"][cvt_setting[11]][1]["java"]["sound_list"]["percussion"]["undefined"]
                            else:
                                if str(note + 21) in asset_list["profile"][cvt_setting[11]][1]["bedrock"]["sound_list"]["percussion"]:
                                    program = asset_list["profile"][cvt_setting[11]][1]["bedrock"]["sound_list"]["percussion"][str(note + 21)]
                                else:
                                    program = asset_list["profile"][cvt_setting[11]][1]["bedrock"]["sound_list"]["percussion"]["undefined"]
                        else:
                            if cvt_setting[7] == 2:
                                program = asset_list["profile"][cvt_setting[11]][1]["java"]["sound_list"]["default"]
                            else:
                                program = asset_list["profile"][cvt_setting[11]][1]["bedrock"]["sound_list"]["default"]
                            for typ in info_list[channel]["program"]:
                                if typ[0] > source_time:
                                    break
                                else:
                                    program = typ[1]
                        if cvt_setting[10]:
                            velocity = int((velocity / 1.27) * volume * total_vol * program[1]) / 100
                        else:
                            velocity = int((velocity / 1.27) * volume * total_vol) / 100
                        if velocity >= 1:
                            velocity = 1
                        if channel == 9:
                            pitch = 1
                        else:
                            if 0 <= note + pitch_offset < note_len:
                                pitch = asset_list["profile"][cvt_setting[11]][1]["note_list"][note + pitch_offset]
                            else:
                                pitch = None
                        if cvt_setting[10] and pitch is not None:
                            pitch *= program[2]
                        tick_time = 0
                        for n in range(1, len(tempo_list)):
                            if tempo_list[n][0] <= source_time:
                                tick_time += tick2second(tempo_list[n][0] - tempo_list[n - 1][0], mid.ticks_per_beat, tempo_list[n - 1][1]) * 2000 / cvt_setting[2]
                            else:
                                tick_time += tick2second(source_time - tempo_list[n - 1][0], mid.ticks_per_beat, tempo_list[n - 1][1]) * 2000 / cvt_setting[2]
                                break
                        tick_time = int(round_45(tick_time - offset_time))
                        if (program[0] != "disable" and (cvt_setting[4] or channel != 9)) and ((cvt_setting[7] != 0 or num <= h - append_num) and (pitch is not None and (cvt_setting[9] == 0 or 0.5 <= pitch <= 2))):
                            if state[3][7] == 3:
                                raw_text = "WD " + to_text(note, 2)
                            else:
                                if cvt_setting[7] == 2:
                                    if cvt_setting[5] == 0:
                                        raw_text = asset_list["profile"][cvt_setting[11]][1]["java"]["command"]["command_delay"]
                                    elif cvt_setting[5] == 1:
                                        raw_text = asset_list["profile"][cvt_setting[11]][1]["java"]["command"]["command_clock"]
                                    elif cvt_setting[5] == 2:
                                        raw_text = asset_list["profile"][cvt_setting[11]][1]["java"]["command"]["command_address"]
                                    else:
                                        raw_text = ""
                                else:
                                    if cvt_setting[5] == 0:
                                        raw_text = asset_list["profile"][cvt_setting[11]][1]["bedrock"]["command"]["command_delay"]
                                    elif cvt_setting[5] == 1:
                                        raw_text = asset_list["profile"][cvt_setting[11]][1]["bedrock"]["command"]["command_clock"]
                                    elif cvt_setting[5] == 2:
                                        raw_text = asset_list["profile"][cvt_setting[11]][1]["bedrock"]["command"]["command_address"]
                                    else:
                                        raw_text = ""
                                raw_text = raw_text.replace("{SOUND}", str(program[0])).replace("{BALANCE}", str(balance)).replace("{VOLUME}", str(velocity)).replace("{PITCH}", str(pitch)).replace("{TIME}", str(tick_time)).replace("{ADDRESS}", str(play_id))
                            if tick_time not in note_buffer:
                                note_buffer[tick_time] = []
                            if tick_time not in time_list:
                                time_list.append(tick_time)
                            note_buffer[tick_time].append(raw_text)
                            num += 1
                        else:
                            if cvt_setting[7] != 0:
                                progress += 1
                        progress += 1
                        progress_bar(message_id, "正在转换 " + midi_name[0:-4], progress, total)
        time_list.sort()
        if cvt_setting[7] == 2:
            if "old_edition" in asset_list["profile"][cvt_setting[11]][1]["description"]["feature"]:
                if cvt_setting[5] == 1:
                    note_buffer[time_list[-1]].append("/scoreboard players set @a[score_MMS_Service_min="
                                                      + str(time_list[-1])
                                                      + "] MMS_Service -1"
                                                      )
                    note_buffer[time_list[-1]].append("/scoreboard players add @a[score_MMS_Service_min=0] MMS_Service 1")
                    total += 2
                    num += 2
                elif cvt_setting[5] == 2:
                    note_buffer[time_list[-1]].append("/scoreboard players set @a[score_MMS_Service_min="
                                                      + str(time_list[-1]) + ","
                                                      + "MMS_Address_min=" + str(play_id)
                                                      + ",score_MMS_Address=" + str(play_id)
                                                      + "] MMS_Service -1"
                                                      )
                    note_buffer[time_list[-1]].append("/scoreboard players add @a[score_MMS_Service_min=0,"
                                                      + "MMS_Address_min=" + str(play_id)
                                                      + ",score_MMS_Address=" + str(play_id)
                                                      + "] MMS_Service 1")
                    total += 2
                    num += 2
            else:
                if cvt_setting[5] == 1:
                    note_buffer[time_list[-1]].append("/scoreboard players set @a[scores={MMS_Service="
                                                      + str(time_list[-1])
                                                      + "..}] MMS_Service -1"
                                                      )
                    note_buffer[time_list[-1]].append("/scoreboard players add @a[scores={MMS_Service=0..}] MMS_Service 1")
                    total += 2
                    num += 2
                elif cvt_setting[5] == 2:
                    note_buffer[time_list[-1]].append("/scoreboard players set @a[scores={MMS_Service="
                                                      + str(time_list[-1]) + "..,"
                                                      + "MMS_Address=" + str(play_id) + "}] MMS_Service -1"
                                                      )
                    note_buffer[time_list[-1]].append("/scoreboard players add @a[scores={MMS_Service=0..,"
                                                      + "MMS_Address=" + str(play_id)
                                                      + "}] MMS_Service 1")
                    total += 2
                    num += 2
        else:
            if cvt_setting[5] == 1:
                note_buffer[time_list[-1]].append("/scoreboard players set @a[scores={MMS_Service="
                                                  + str(time_list[-1])
                                                  + "..}] MMS_Service -1"
                                                  )
                note_buffer[time_list[-1]].append("/scoreboard players add @a[scores={MMS_Service=0..}] MMS_Service 1")
                num += 2
                if cvt_setting[7] == 1:
                    total += 2
            elif cvt_setting[5] == 2:
                note_buffer[time_list[-1]].append("/scoreboard players set @a[scores={MMS_Service="
                                                  + str(time_list[-1]) + "..,"
                                                  + "MMS_Address=" + str(play_id) + "}] MMS_Service -1"
                                                  )
                note_buffer[time_list[-1]].append("/scoreboard players add @a[scores={MMS_Service=0..,"
                                                  + "MMS_Address=" + str(play_id)
                                                  + "}] MMS_Service 1")
                num += 2
                if cvt_setting[7] == 1:
                    total += 2
        if cvt_setting[7] == 0:
            del_list = []
            s = (structure["size"][0].value,
                 structure["size"][1].value,
                 structure["size"][2].value)
            p = [0, 0, 0]
            for n in structure["structure"]["palette"]["default"]["block_position_data"]:
                i = structure["structure"]["palette"]["default"]["block_position_data"][n]["block_entity_data"]
                if i["CustomName"].value == "start":
                    p[0] = i["x"].value - structure["structure_world_origin"][0].value
                    p[1] = i["y"].value - structure["structure_world_origin"][1].value
                    p[2] = i["z"].value - structure["structure_world_origin"][2].value
                elif i["CustomName"].value == "append":
                    i["Command"] = TAG_String(i["Command"].value.replace("__ADDRESS__", str(play_id)))
                    i["Command"] = TAG_String(i["Command"].value.replace("__NAME__", str(path.splitext(midi_name)[0])))
                    i["Command"] = TAG_String(i["Command"].value.replace("__TOTAL__", str(time_list[-1])))
                    del_list.append(list_position(s, (
                        i["x"].value - structure["structure_world_origin"][0].value,
                        i["y"].value - structure["structure_world_origin"][1].value,
                        i["z"].value - structure["structure_world_origin"][2].value
                    )))
                    progress += 1
                    progress_bar(message_id, "正在转换 " + midi_name[0:-4], progress, total)
                i["CustomName"] = TAG_String("")
            n = 0
            air_palette = -1
            for n, i in enumerate(structure["structure"]["palette"]["default"]["block_palette"]):
                if i["name"].value == "minecraft:air":
                    air_palette = n
                    break
            if air_palette == -1:
                air_palette = n + 1
                structure["structure"]["palette"]["default"]["block_palette"].append(
                    TAG_Compound({
                        "name": TAG_String("minecraft:air"),
                        "states": TAG_Compound(),
                        "val": TAG_Short(0),
                        "version": TAG_Int(18090528)
                    })
                )
            i = 1
            real_time = 0
            for source_time in time_list:
                for n, cmd in enumerate(note_buffer[source_time]):
                    if structure["structure"]["palette"]["default"]["block_position_data"].get(str(list_position(s, p))) and check(s, p):
                        if cvt_setting[5] != 0 or n != 0:
                            output_time = 0
                        else:
                            output_time = source_time - real_time
                        real_time += output_time
                        structure["structure"]["palette"]["default"]["block_position_data"][str(list_position(s, p))]["block_entity_data"]["Command"] = TAG_String(cmd)
                        structure["structure"]["palette"]["default"]["block_position_data"][str(list_position(s, p))]["block_entity_data"]["TickDelay"] = TAG_Int(output_time)
                        if cvt_setting[6]:
                            if i == 1:
                                structure["structure"]["palette"]["default"]["block_position_data"][str(list_position(s, p))]["block_entity_data"]["CustomName"] = TAG_String(path.splitext(midi_name)[0])
                            else:
                                structure["structure"]["palette"]["default"]["block_position_data"][str(list_position(s, p))]["block_entity_data"]["CustomName"] = TAG_String(str(i) + "/" + str(num))
                        del_list.append(list_position(s, p))
                        direct = structure["structure"]["palette"]["default"]["block_palette"][structure["structure"]["block_indices"][0][list_position(s, p)].value]["states"]["facing_direction"].value
                        if direct == 0:
                            p[1] -= 1
                        elif direct == 1:
                            p[1] += 1
                        elif direct == 2:
                            p[2] -= 1
                        elif direct == 3:
                            p[2] += 1
                        elif direct == 4:
                            p[0] -= 1
                        elif direct == 5:
                            p[0] += 1
                        i += 1
                        progress += 1
                        progress_bar(message_id, "正在转换 " + midi_name[0:-4], progress, total)
                    else:
                        break
            for n in range(h, -1, -1):
                if n not in del_list:
                    if str(n) in structure["structure"]["palette"]["default"]["block_position_data"]:
                        del structure["structure"]["palette"]["default"]["block_position_data"][str(n)]
                    structure["structure"]["block_indices"][0][n] = TAG_Int(air_palette)
                    structure["structure"]["block_indices"][1][n] = TAG_Int(-1)
                    progress += 1
                    progress_bar(message_id, "正在转换 " + midi_name[0:-4], progress, total)
            with open(output_name + ".mcstructure", "wb") as io:
                structure.save(io, little_endian=True)
        elif cvt_setting[7] == 1:
            if path.exists(output_name):
                rmtree(output_name)
            makedirs(output_name)
            makedirs(output_name + "/functions")
            with open(output_name + "/functions/mms_player.mcfunction", "w", encoding="utf-8") as io:
                for source_time in time_list:
                    for cmd in note_buffer[source_time]:
                        io.write(cmd[1:] + "\n")
                        progress += 1
                        progress_bar(message_id, "正在转换 " + midi_name[0:-4], progress, total)
            with open(output_name + "/world_behavior_packs.json", "w") as io:
                io.write(dump_bytes(behavior))
            with open(output_name + "/manifest.json", "w") as io:
                io.write(dump_bytes(manifest))
        elif cvt_setting[7] == 2:
            if "old_edition" in asset_list["profile"][cvt_setting[11]][1]["description"]["feature"]:
                if path.exists(output_name):
                    rmtree(output_name)
                makedirs(output_name)
                makedirs(output_name + "/mms")
                with open(output_name + "/mms/player.mcfunction", "w", encoding="utf-8") as io:
                    for source_time in time_list:
                        for cmd in note_buffer[source_time]:
                            io.write(cmd[1:] + "\n")
                            progress += 1
                            progress_bar(message_id, "正在转换 " + midi_name[0:-4], progress, total)
            else:
                if path.exists(output_name):
                    rmtree(output_name)
                makedirs(output_name)
                makedirs(output_name + "/data")
                makedirs(output_name + "/data/mms")
                makedirs(output_name + "/data/mms/functions")
                with open(output_name + "/data/mms/functions/player.mcfunction", "w", encoding="utf-8") as io:
                    for source_time in time_list:
                        for cmd in note_buffer[source_time]:
                            io.write(cmd[1:] + "\n")
                            progress += 1
                            progress_bar(message_id, "正在转换 " + midi_name[0:-4], progress, total)
                with open(output_name + "/pack.mcmeta", "w") as io:
                    io.write(dump_bytes(behavior))
        elif cvt_setting[7] == 3:
            progress_bar(message_id, "正在连接 " + asset_list["serial_list"][state[3][8]][1], progress, total)
            with Serial(asset_list["serial_list"][state[3][8]][0], baudrate=9600, parity=PARITY_EVEN) as device:
                if device.is_open:
                    device.write(b"CR")
                    sleep(0.1)
                    if device.read_all().decode() == "IC":
                        progress_bar(message_id, "已连接 " + device.name, progress, total)
                        tick_time = 0
                        for source_time in time_list:
                            for n, cmd in enumerate(note_buffer[source_time]):
                                if n == 0:
                                    output_time = source_time - tick_time
                                else:
                                    output_time = 0
                                cmd += to_text(output_time, 3)
                                device.write(cmd.encode())
                                i = 0
                                while not device.in_waiting:
                                    if i >= 100:
                                        convertor_state = "连接设备超时"
                                        return
                                    i += 1
                                    sleep(0.001)
                                device.reset_input_buffer()
                                progress += 1
                                progress_bar(message_id, "写入中 " + midi_name[0:-4], progress, total)
                            tick_time = source_time
                    else:
                        convertor_state = "连接设备失败"
                        return
        del mid
        del info_list
        del time_list
        del structure
        del tempo_list
        del note_buffer
        del velocity_list
        collect()
        convertor_state = False
    except Exception:
        save_log(3, "E:", format_exc())
    finally:
        if convertor_state is False:
            message_list.append(("转换完成，文件已保存在程序运行目录下！", message_id))
            try:
                # try to detect output file or folder
                # try to detect output file or folder
                outfile = None
                if 'output_name' in locals():
                    try:
                        candidate = output_name + ".mcstructure"
                        if path.exists(candidate):
                            outfile = path.abspath(candidate)
                        elif path.exists(output_name) and path.isdir(output_name):
                            # convert directory output into a zip archive for download
                            zip_base = output_name
                            try:
                                make_archive(zip_base, 'zip', output_name)
                                outfile = path.abspath(zip_base + '.zip')
                            except Exception:
                                outfile = path.abspath(output_name)
                        elif path.exists(output_name):
                            outfile = path.abspath(output_name)
                        else:
                            outfile = path.abspath(output_name)
                    except Exception:
                        outfile = None
                if 'api_tasks' in globals() and message_id in api_tasks:
                    api_tasks[message_id]['status'] = 'done'
                    api_tasks[message_id]['output'] = outfile
            except Exception:
                pass
        else:
            if convertor_state is True:
                convertor_state = "未知错误"
            message_list.append(("因" + convertor_state + "无法转换 " + midi_name[0:-4], message_id))
            try:
                if 'api_tasks' in globals() and message_id in api_tasks:
                    api_tasks[message_id]['status'] = 'failed'
                    api_tasks[message_id]['error'] = str(convertor_state)
            except Exception:
                pass

def round_45(i, n=0):
    i = int(i * 10 ** int(n + 1))
    if i % 10 >= 5:
        i += 10
    i = int(i / 10)
    return float(i / (10 ** int(n)))

def progress_bar(mess_id, title, pss, tal):
    try:
        if len(message_list) != 0 and message_list[0][1] == mess_id:
            if pss == tal:
                if len(message_list) > 1 and message_list[1][1] == mess_id:
                    state[8][0] = 3250
                else:
                    state[8][0] = 3000
            else:
                message_list[0][0] ="[" + str(int((pss / tal) * 100)) + "%] " + title
                state[8][0] = 0
        elif len(message_list) == 0:
            message_list.append(["[" + str(int((pss / tal) * 100)) + "%] " + title, mess_id])
    except Exception:
        pass

def save_log(log_pos, log_type, log_info):
    if log[0][1]:
        log[0][0] = True
        log[log_pos].append(log_type)
        for i in log_info.splitlines():
            log[log_pos].append("  " + i)

def save_json():
    try:
        asset_list["setting"]["setting"]["fps"] = asset_list["fps"]
        asset_list["setting"]["setting"]["auto_gain"] = state[3][0]
        asset_list["setting"]["setting"]["speed"] = state[3][2]
        asset_list["setting"]["setting"]["skip"] = int(state[3][3])
        asset_list["setting"]["setting"]["enable_percussion"] = int(state[3][4])
        asset_list["setting"]["setting"]["mode"] = state[3][5]
        asset_list["setting"]["setting"]["append_number"] = int(state[3][6])
        asset_list["setting"]["setting"]["file_type"] = state[3][7]
        asset_list["setting"]["setting"]["adjust_pitch"] = state[3][9]
        asset_list["setting"]["setting"]["adjust_instrument"] = int(state[3][10])
        with open("Asset/text/setting.json", "w") as io:
            io.write(dump_bytes(asset_list["setting"], indent=2))
    except Exception:
        save_log(5, "E:", format_exc())

def to_text(i, n):
    i = str(i)
    if len(i) < n:
        i = "0" * (n - len(i)) + i
    else:
        i = i[-n:]
    return i

def download():
    try:
        if path.exists("Asset/update"):
            rmtree("Asset/update")
        makedirs("Asset/update")
        state[6][0] = 0
        if "hash" in state[5]:
            target_hash = state[5]["hash"]
        else:
            target_hash = "disable"
        real_hash = md5()
        response = get(state[5]["download_url"], stream=True)
        state[6][1] = int(response.headers['content-length'])
        with open("Asset/update/package.7z", 'ab') as io:
            for chunk in response.iter_content(chunk_size=1024):
                io.write(chunk)
                real_hash.update(chunk)
                state[6][0] += len(chunk)
        real_hash = str(real_hash.hexdigest())
        if target_hash != "disable" and real_hash != target_hash:
            raise ValueError("The Expected Hash is " + str(target_hash) + ", But the Hash of Downloaded FIle is " + str(real_hash) + ".")
        message_list.append(("下载完成，即将进行更新。", -1))
        state[7] = 2
    except Exception:
        state[6] = [0, 0, True]
        message_list.append(("下载失败，请重试。", -1))
        save_log(4, "E:", format_exc())


def list_position(size, pos):
    n = pos[2]
    n += pos[1] * size[2]
    n += pos[0] * (size[1] * size[2])
    return n

def position(size, pos):
    l = [0, 0, 0]
    l[0] = pos // (size[1] * size[2])
    pos = pos % (size[1] * size[2])
    l[1] = pos // size[2]
    pos = pos % size[2]
    l[2] += pos
    return l

def check(size, pos):
    if pos[0] >= size[0] or pos[0] < 0:
        return False
    elif pos[1] >= size[1] or pos[1] < 0:
        return False
    elif pos[2] >= size[2] or pos[2] < 0:
        return False
    else:
        return True

# GUI 函数已删除









def uuid(n):
    cmd = ""
    while not n == 0:
        cmd += str(hex(randint(0, 15)))[2:]
        n -= 1
    return cmd

log = [[False, True], ["Loading:"], ["Main:"], ["Convertor:"], ["Updater:"], ["Other:"]]
state = [0, [0, 0, -1], "init", [0, 0, 100, True, 0, 0, False, 0, 0, 0, 0, 0], False, None, [0, 0, True], 0, [0, 0], -1]

# API task registry for external requests
api_tasks = {}
# uploads folder for API
api_upload_dir = "api_uploads"
try:
    if not path.exists(api_upload_dir):
        makedirs(api_upload_dir)
except Exception:
    pass
# API bind settings
api_host = '127.0.0.1'
api_port = 1080

# Initialize global variables
asset_list = {"fps": 60}
message_list = []
task_id = 0

try:
    # 加载配置资源
    asset_load()

    print("✓ MIDI-MCSTRUCTURE API 服务启动中...")
    # 自动检测端口是否被占用，若被占用则递增端口号
    def find_free_port(host, start_port, max_tries=20):
        import socket
        port = start_port
        for _ in range(max_tries):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind((host, port))
                s.close()
                return port
            except OSError:
                port += 1
                s.close()
        return None

    if Flask is not None:
        def _start_api():
            app = Flask(__name__)
            if CORS is not None:
                CORS(app, resources={r"/*": {"origins": "*"}})

            @app.route('/midi', methods=['POST'])
            def upload_midi():
                try:
                    if 'file' not in request.files:
                        return jsonify({'error': 'no file field'}), 400
                    f = request.files['file']
                    if f.filename == '':
                        return jsonify({'error': 'empty filename'}), 400
                    filename = secure_filename(f.filename)
                    save_path = path.join(api_upload_dir, filename)
                    f.save(save_path)
                    # create task
                    global task_id
                    task_id += 1
                    api_tasks[task_id] = {'status': 'queued', 'output': None, 'error': None, 'filename': filename}
                    Thread(target=convertor, args=(api_upload_dir + '/', filename, state[3], task_id)).start()
                    return jsonify({'task_id': task_id, 'filename': filename, 'status': 'queued', 'output': None, 'error': None}), 200
                except Exception as e:
                    return jsonify({'error': str(e)}), 500

            @app.route('/check/<int:tid>', methods=['GET'])
            def check_task(tid):
                if tid not in api_tasks:
                    return jsonify({'error': 'unknown task id'}), 404
                info = api_tasks[tid].copy()
                # if done and output is a file, build download URL
                if info.get('status') == 'done' and info.get('output'):
                    out = info.get('output')
                    # if output is an absolute or relative path, return a URL if file exists
                    if out and path.exists(out):
                        # use request.host_url as base
                        info['download_url'] = request.host_url.rstrip('/') + '/files/' + path.basename(out)
                return jsonify(info), 200

            @app.route('/files/<path:fname>', methods=['GET'])
            def serve_file(fname):
                # serve from current working dir or upload dir
                candidates = [path.abspath('.'), path.abspath(api_upload_dir)]
                for d in candidates:
                    if path.exists(path.join(d, fname)):
                        return send_from_directory(d, fname, as_attachment=True)
                return ("Not found", 404)

            @app.route('/', methods=['GET'])
            def serve_test_page():
                # serve a simple HTML test page bundled in repo root
                try:
                    if path.exists(path.join(path.abspath('.'), 'api_test.html')):
                        return send_from_directory(path.abspath('.'), 'api_test.html')
                except Exception:
                    pass
                return ("<html><body><h3>API test page not found</h3></body></html>", 200)

            # 查找可用端口
            global api_port
            free_port = find_free_port(api_host, api_port)
            if free_port is None:
                print(f"✗ 未找到可用端口（尝试范围：{api_port}-{api_port+19}），API服务无法启动。")
                return
            api_port = free_port
            print(f"✓ API 地址: http://{api_host}:{api_port}")
            print("✓ 可用端点: POST /midi (上传), GET /check/<task_id> (查询), GET /files/<filename> (下载)")
            app.run(host=api_host, port=api_port, threaded=True)

        Thread(target=_start_api, daemon=True).start()

        # 保持主线程运行
        try:
            while True:
                sleep(1)
        except KeyboardInterrupt:
            print("\n✓ API 服务已停止")
    else:
        print("✗ Flask 未安装，无法启动 API 服务")

except Exception:
    save_log(2, "E:", format_exc())
finally:
    if not log[0][0]:
        save_json()
    if log[0][0] and log[0][1]:
        with open("log.txt", "a") as file:
            for texts in log[1:]:
                if len(texts) == 1:
                    texts.append("None")
                for m, text in enumerate(texts):
                    if m != 0:
                        text = "  " + text
                    file.write(str(text) + "\n")
    _exit(0)