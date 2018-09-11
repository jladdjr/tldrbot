#!/usr/bin/env python
import os
import time

from slackclient import SlackClient

channels = [('channel-name', 'C0000000000')]

slack_token = os.environ["SLACK_TOKEN"]
sc = SlackClient(slack_token)

def check_channel(channel):
    channel_name, channel_id = channel
    print('Reading {}'.format(channel_name))

    if channel_id[0] == 'G':
        api_method = 'groups.history'
    elif channel_id[0] == 'C':
        api_method = 'channels.history'
    else:
        raise Exception('Do not recognize channel type for {0} ({1})'.format(channel_id, channel_name))
    conv_history = sc.api_call(api_method, channel=channel_id)

    timestamps = []
    backoff_period = 0
    current_time = time.time()
    for msg in reversed(conv_history['messages']):
        timestamp = float(msg['ts'])

        if current_time - timestamp > 60 * 5:
            continue

        timestamps.append(timestamp)

        if len(timestamps) < 10:
            continue

        if (timestamp > backoff_period) and \
           (timestamp - timestamps[0] < 30 *  9):
            avg_rate = (timestamp - timestamps[0]) / 9.0
            backoff_period = timestamp + 180
            timestamp_str = time.strftime('%H:%M:%S', time.localtime(timestamp))
            notice = u"""In <#{0}|{1}>, at {2}, "{3}" (_rate: {4} sec/msg_)""".format(channel_id, channel_name, timestamp_str, msg['text'], int(avg_rate))

            print(notice)
            sc.api_call(
              "chat.postMessage",
              channel="D1EPGDKGB", # jim
              text=notice
            )
            time.sleep(5)

        timestamps.pop(0)

while True:
    for channel in channels:
        check_channel(channel)
        time.sleep(5)
    print("---------------------------------------")
    time.sleep(60 * 5)

