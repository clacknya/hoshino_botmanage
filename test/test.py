#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import random
import pprint
import asyncio
import aiohttp
import logging
import coloredlogs
import linecache
import tracemalloc

PATH_ROOT = os.path.dirname(os.path.abspath(__file__))

def display_top(snapshot, key_type='lineno', limit=10):
	snapshot = snapshot.filter_traces((
		tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
		tracemalloc.Filter(False, "<unknown>"),
	))
	top_stats = snapshot.statistics(key_type)

	print("Top %s lines" % limit)
	for index, stat in enumerate(top_stats[:limit], 1):
		frame = stat.traceback[0]
		print("#%s: %s:%s: %.1f KiB"
			  % (index, frame.filename, frame.lineno, stat.size / 1024))
		line = linecache.getline(frame.filename, frame.lineno).strip()
		if line:
			print('    %s' % line)

	other = top_stats[limit:]
	if other:
		size = sum(stat.size for stat in other)
		print("%s other: %.1f KiB" % (len(other), size / 1024))
	total = sum(stat.size for stat in top_stats)
	print("Total allocated size: %.1f KiB" % (total / 1024))

# https://github.com/botuniverse/onebot/blob/master/legacy/v10/specs/event/message.md
# https://github.com/Mrs4s/go-cqhttp/blob/master/coolq/event.go
# https://github.com/Mrs4s/MiraiGo/blob/master/message/message.go

def generate_groups(group_num: int=4, member_num: int=4, addition: list[int]=[]) -> dict:
	return dict(map(
		lambda k: (k, random.sample(range(1, 10000), member_num) + addition),
		random.sample(range(1, 10000), group_num)
	))

class FakeClient():

	pp = pprint.PrettyPrinter(indent=4)
	logger = logging.getLogger('FakeClient')

	BOT = {
		'uid': 114514,
	}

	MASTER = {
		'uid': 10000,
	}

	GROUPS = generate_groups(4, 4, [BOT['uid'], MASTER['uid']])
	GROUPS.update({
		10086: [1, 2, 3, 4, 5] + [BOT['uid'], MASTER['uid']],
	})

	HOST = '127.0.0.1'
	PORT = '8080'

	MSG_ID_SEQ = iter(range(10000))
	MSG_CODE = {
		100: {'msg': 'EMPTY_MSG_ERROR', 'wording': '消息为空'},
	}
	REQ_ID_SEQ = iter(range(10000))

	@classmethod
	def new_message_id(cls) -> int:
		return next(cls.MSG_ID_SEQ)

	@classmethod
	def new_request_id(cls) -> int:
		return next(cls.REQ_ID_SEQ)

	@classmethod
	def msg_reply_ok(cls) -> dict:
		return {
			'data': {
				'message_id': cls.new_message_id(),
			},
			'retcode': 0,
			'status': 'ok',
		}

	@classmethod
	def msg_reply_failed(cls, code: int) -> dict:
		return {
			'data': None,
			'retcode': code,
			'msg': cls.MSG_CODE[code]['msg'],
			'wording': cls.MSG_CODE[code]['wording'],
			'status': 'failed'
		}

	@classmethod
	def private_msg_pack(cls, target_id: int, sender_id: int, sub_type: str, msg) -> dict:
		data = {
			'time': int(time.time()),
			'self_id': cls.BOT['uid'],
			'post_type': 'message',
			'message_type': 'private',
			'sub_type': sub_type,
			'message_id': cls.new_message_id(),
			'target_id': target_id,
			'user_id': sender_id,
			'anonymous': None,
			'message': msg,
			'raw_message': msg,
			'font': 0,
			'sender': {
				'user_id': sender_id,
				'nickname': sender_id,
				'card': 'rc',
				'sex': 'female',
				'age': 24,
				'area': '下北泽',
				'level': '是学生',
				'role': 'owner',
				'title': 'global rc'
			}
		}
		return data

	@classmethod
	def group_msg_pack(cls, group_id: int, sender_id: int, msg) -> dict:
		data = {
			'time': int(time.time()),
			'self_id': cls.BOT['uid'],
			'post_type': 'message',
			'message_type': 'group',
			'sub_type': 'normal',
			'message_id': cls.new_message_id(),
			'group_id': group_id,
			'user_id': sender_id,
			'anonymous': None,
			'message': msg,
			'raw_message': msg,
			'font': 0,
			'sender': {
				'user_id': sender_id,
				'nickname': sender_id,
				'card': 'rc',
				'sex': 'female',
				'age': 24,
				'area': '下北泽',
				'level': '是学生',
				'role': 'owner',
				'title': 'global rc'
			}
		}
		return data

	@classmethod
	def get_group_member_info(cls, group_id: int, user_id: int, no_cache: bool, self_id: int):
		members = cls.GROUPS.get(group_id, {})
		index = members.index(user_id)
		return {
			'group_id': group_id,
			'user_id': user_id,
			'nickname': user_id,
			'card': user_id,
			'sex': 'unknown',
			'area': '未知',
			'join_time': int(time.time()),
			'last_sent_time': int(time.time()),
			'level': 'LVMAX',
			'role': 'owner' if index == 0 else 'admin' if index == 1 else 'member',
			'unfriendly': False,
			'title': '',
			'title_expire_time': int(time.time()),
			'card_changeable': True,
		}

	@classmethod
	async def receive(cls):
		while not cls.ws.closed:
			recv = await cls.ws.receive_json()
			cls.logger.info('recv data')
			cls.pp.pprint(recv)
			if recv['action'] == '.handle_quick_operation_async':
				ret = {
					'data': None,
					'retcode': 1,
					'status': 'async',
					'echo': recv.get('echo'),
				}
				await cls.send(ret)
				cls.logger.warning('operation finish')
				continue
			ret = cls.msg_reply_ok()
			ret['echo'] = recv.get('echo')
			if recv['action'] == 'send_msg':
				data = recv['params']
				if data['message_type'] in ['group', 'private']:
					await cls.send(ret)
				else:
					cls.logger.error(f"Unkown message_type: {data['message_type']}")
			elif recv['action'] == 'send_private_msg':
				await cls.send(ret)
			elif recv['action'] == 'get_group_member_info':
				ret['data'].update(cls.get_group_member_info(**recv['params']))
				await cls.send(ret)
			else:
				cls.logger.error(f"Unkown action: {recv['action']}")

	@classmethod
	async def send(cls, data: dict):
		cls.logger.info('send data')
		await cls.ws.send_json(data)

	@classmethod
	async def run(cls):
		url = f"http://{cls.HOST}:{cls.PORT}/ws"
		headers = {
			'Host': f"{cls.HOST}:{cls.PORT}",
			'Connection': 'Upgrade',
			'Upgrade': 'websocket',
			'X-Self-ID': f"{cls.BOT['uid']}",
			'X-Client-Role': 'Universal'
		}
		enable = {
			'time': time.time(),
			'self_id': cls.BOT['uid'],
			'post_type': 'meta_event',
			'meta_event_type': ' lifecycle',
			'sub_type': 'enable'
		}
		async with aiohttp.ClientSession() as session:
			async with session.ws_connect(url, headers=headers) as ws:
				cls.ws = ws
				await cls.ws.send_json(enable)
				receiver = asyncio.create_task(cls.receive())
				await cls.job()
				receiver.cancel()

	@classmethod
	async def call_help(cls):
		await cls.send(cls.group_msg_pack(
			group_id=random.choice(list(cls.GROUPS.keys())),
			sender_id=cls.MASTER['uid'],
			msg='help',
		))

	@classmethod
	async def call_ls(cls):
		await cls.send(cls.group_msg_pack(
			group_id=random.choice(list(cls.GROUPS.keys())),
			sender_id=cls.MASTER['uid'],
			msg='lssv',
		))

	@classmethod
	async def group_invite_test(cls):
		group_id = random.choice(list(cls.GROUPS.keys()))
		user_id = random.choice(cls.GROUPS[group_id])
		cls.logger.debug(f"group data: {cls.GROUPS[group_id]}")
		await cls.send({
			'time': int(time.time()),
			'self_id': cls.BOT['uid'],
			'post_type': 'request',
			'request_type': 'group',
			'sub_type': 'invite',
			'group_id': group_id,
			'user_id': user_id,
			'comment': '',
			'flag': str(cls.new_request_id()),
		})
		await asyncio.sleep(1)
		await cls.send(cls.private_msg_pack(
			target_id=cls.BOT['uid'],
			sender_id=cls.MASTER['uid'],
			sub_type='friend',
			# msg='同意群邀请',
			msg='拒绝群邀请',
		))
		await asyncio.sleep(5)
		await cls.send(cls.private_msg_pack(
			target_id=cls.BOT['uid'],
			sender_id=cls.MASTER['uid'],
			sub_type='friend',
			msg='待处理群邀请数',
		))
		await cls.send(cls.private_msg_pack(
			target_id=cls.BOT['uid'],
			sender_id=cls.MASTER['uid'],
			sub_type='friend',
			# msg='允许加群 12345',
			msg='禁止加群 12345',
		))
		await cls.send(cls.private_msg_pack(
			target_id=cls.BOT['uid'],
			sender_id=cls.MASTER['uid'],
			sub_type='friend',
			# msg='允许加群 12345',
			msg='禁止加群 12345',
		))

	@classmethod
	async def job(cls):
		tasks = [
			asyncio.create_task(asyncio.sleep(30)),
			asyncio.create_task(cls.group_invite_test()),
		]
		await asyncio.gather(*tasks)

async def main():
	coloredlogs.install(level='DEBUG')
	await FakeClient.run()

if __name__ == '__main__':
	# tracemalloc.start()
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		pass
	# snapshot = tracemalloc.take_snapshot()
	# display_top(snapshot)
