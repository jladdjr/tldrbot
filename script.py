#!/usr/bin/env python

import logging
import os
import time

from slackclient import SlackClient

logger = logging.getLogger(__name__)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
logger.addHandler(ch)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
#channels = [('channel_name', 'C0000000000')]
#users = [('user_name', 'U0000000000')]

slack_token = os.environ["SLACK_TOKEN"]
sc = SlackClient(slack_token)

class SlackChannel(object):

    def __init__(self, channel_id, channel_name=None):
        self.channel_id = channel_id
        self.channel_name = channel_name if channel_name else ''

    def __str__(self):
        if self.channel_name:
            return self.channel_name
        return self.channel_id

    def history(self, since=None):
        logger.info(u'Getting messages for channel {}'.format(self))
        if self.channel_id[0] == 'G':
            api_method = 'groups.history'
        elif self.channel_id[0] == 'C':
            api_method = 'channels.history'
        else:
            raise Exception('Do not recognize channel type for {0} ({1})'.format(channel_id, channel_name))

        params = dict(channel=self.channel_id)
        if since:
            params['oldest'] = since

        logger.debug(u'Calling {0} on {1} ({2})'.format(api_method, self.channel_id, params))
        return sc.api_call(api_method, **params)

class ChannelScraper(object):
    
    def __init__(self, strategy, slack_channel, since=None, interval=30):
        self.strategy = strategy
        self.slack_channel = slack_channel
        self.last_timestamp = since if since else time.time()
        self.interval = interval

    def scrape(self):
        logger.info(u'Begin scrapping {}'.format(self.slack_channel))
        if time.time() - self.last_timestamp < self.interval:
            return

        history = slack_channel.history(since=self.last_timestamp)
        self.last_timestamp = time.time()

        self.strategy.scan(reversed(history['messages']))
        logger.info(u'Finished scrapping {}'.format(self.slack_channel))

class Strategy(object):

    def __init__(self):
        self.callbacks = []

    def register_callback(self, callback):
        self.callbacks.append(callback)

    def deregister_callback(self, callback):
        self.callbacks.remove(callback)
    
    def _trigger(self, text):
        for cb in self.callbacks:
            cb(text)

    def scan(self, messages):
        pass

class NaturalBreaksStrategy(Strategy):

    def __init__(self, max_cache_length=500, break_length=5*60):
        super(NaturalBreaksStrategy, self).__init__()
        self.message_cache = []
        self.max_cache_length = max_cache_length
        self.break_length = break_length

    def __str__(self):
        return 'NaturalBreaksStrategy'

    def scan(self, messages):
        if type(messages) is not list:
            messages = list(messages)
        logger.info(u'{}: Begin scanning'.format(self))

        if not self.message_cache:
            last_ts = float(messages[0]['ts'])
        else:
            last_ts = float(self.message_cache[-1]['ts'])

        self.message_cache.append(messages)
        if len(self.message_cache) > self.max_cache_length:
            self.message_cache = self.message_cache[-self.max_cache_length:]
        
        for msg in messages:
            ts = float(msg['ts'])
            if ts - last_ts > self.break_length:
                logger.info(u'{}: Found natural break: {}'.format(self, msg['text']))
                logger.debug(u'{}: Triggering callbacks'.format(self))
                self._trigger(msg)
                logger.debug(u'{}: Finished triggering callbacks'.format(self))
            last_ts = ts

        logger.info(u'{}: Finished scanning'.format(self))


class SlackNotificationCallbackFactory(object):

    def _get_user_name(self, user_id):
        user = sc.api_call("users.profile.get", user=user_id)
        return user['profile']['real_name']

    @classmethod
    def getCallback(cls, dest_channel_id, src_channel_id, src_channel_name):
        def _callback(msg):
            if not 'user' in msg or not 'text' in msg:
                return
            timestamp_str = time.strftime('%H:%M:%S', time.localtime(float(msg['ts'])))
            text = u'<@{0}>: In <#{1}|{2}>, at {3}, "{4}"'.format(msg['user'], src_channel_id,
                                                                  src_channel_name, timestamp_str,
                                                                  msg['text'])
            sc.api_call("chat.postMessage", channel=dest_channel_id, text=text)
        return _callback


cb = SlackNotificationCallbackFactory.getCallback('D1EPGDKGB', 'C0H0TG8CV', 'tower_api_internal')

strategy = NaturalBreaksStrategy()
strategy.register_callback(cb)

#slack_channel = SlackChannel('C0H0TG8CV', 'tower_api_internal')
slack_channel = SlackChannel('C0F7S8BT5', 'ship_it')
#slack_channel = SlackChannel('C0SNM2FM4', 'test_notifications2')

scraper = ChannelScraper(strategy, slack_channel, since=time.time() - 10*60*60)
scraper.scrape()
