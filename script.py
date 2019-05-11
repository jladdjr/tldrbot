#!/usr/bin/env python

import logging
import os
import time

from slackclient import SlackClient

logger = logging.getLogger('tldrbot')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

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


class ScoredMessage(object):

    def __init__(self, score, msg, callback):
        self.score = 0
        self.msg = msg
        self.callback = callback

    def upvote(self):
        self.score += 1
        self.callback(self.score, self.msg)


class ScoredMessages(object):

    def __init__(self, threshold=1, max_length=500, callbacks=None):
        self.messages = []
        self.threshold = threshold
        self.max_length = max_length
        self.last_read = -1
        self.callbacks = callbacks if type(callbacks) is list else [callbacks]

    def __str__(self):
        return u'\n'.join([u'{0}\t{1:125.125}'.format(m.score, m.msg['text']) for m in self.messages])

    def extend(self, msgs):
        msgs = msgs if type(msgs) is list else list(msgs)
        # increase buffer if necessary
        if len(msgs) > self.max_length:
            self.max_length = len(msgs)

        self.last_read = len(self.messages) - 1

        def _upvote_hook(new_score, msg):
            if new_score == self.threshold:
                for cb in self.callbacks:
                    cb(msg)
        self.messages.extend([ScoredMessage(0, msg, _upvote_hook) for msg in msgs])

        if len(self.messages) > self.max_length:
            self.last_read -= len(self.messages) - len(self.max_length)
            self.messages = self.messages[-self.max_length:]

    def getCurrentBatch(self):
        return self.messages[self.last_read+1:]


class ChannelScraper(object):

    def __init__(self, slack_channel, strategies=None, interval=30, callbacks=None, since=None):
        self.slack_channel = slack_channel
        self.strategies = strategies if type(strategies) is list else [strategies]
        self.messages = ScoredMessages(callbacks=callbacks)
        self.last_timestamp = since if since else time.time()
        self.interval = interval

    def scrape(self):
        logger.info(u'Begin scraping {}'.format(self.slack_channel))

        if time.time() - self.last_timestamp < self.interval:
            return

        messages = slack_channel.history(since=self.last_timestamp)['messages']
        self.messages.extend(reversed(list(messages)))

        self.last_timestamp = time.time()

        for strategy in self.strategies:
            strategy.scan(self.messages)
        logger.info(u'Finished scraping {}'.format(self.slack_channel))

        logger.info(u'ScoredMessages:\n{}'.format(self.messages))

class Strategy(object):

    def __init__(self):
        self.callbacks = []

    def scan(self, messages):
        pass

class NaturalBreaksStrategy(Strategy):

    def __init__(self, break_length=10*60):
        super(NaturalBreaksStrategy, self).__init__()
        self.break_length = break_length

    def __str__(self):
        return 'NaturalBreaksStrategy'

    def scan(self, messages):
        logger.info(u'{}: Begin scanning'.format(self))
        messages = messages.getCurrentBatch()

        last_ts = float(messages[0].msg['ts'])

        for msg in messages:
            ts = float(msg.msg['ts'])
            if ts - last_ts > self.break_length:
                logger.info(u'{}: Found natural break: {}'.format(self, msg.msg['text']))
                msg.upvote()
            last_ts = ts

        logger.info(u'{}: Finished scanning'.format(self))

class ReactionsAreGood(Strategy):

    def __init__(self):
        super(ReactionsAreGood, self).__init__()

    def __str__(self):
        return 'ReactionsAreGood'

    def scan(self, messages):
        logger.info(u'{}: Begin scanning'.format(self))
        messages = messages.getCurrentBatch()

        for msg in messages:
            if 'reactions' in msg.msg:
                for _ in range(len(msg.msg['reactions']) / 2): # TODO
                    msg.upvote()

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

def noop_callback(msg):
    pass

slack_channel = SlackChannel('C0H0TG8CV', 'tower_api_internal')
#slack_channel = SlackChannel('C0F7S8BT5', 'ship_it')
#slack_channel = SlackChannel('C0SNM2FM4', 'test_notifications2')

strategies = [NaturalBreaksStrategy(),
              ReactionsAreGood()]

#cb = SlackNotificationCallbackFactory.getCallback('D1EPGDKGB', 'C0H0TG8CV', 'tower_api_internal')
cb = noop_callback
start_time = time.time() - 10 * 60 * 60

scraper = ChannelScraper(slack_channel,
                         strategies=strategies,
                         callbacks=cb,
                         since=start_time)
scraper.scrape()
