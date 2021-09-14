#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Dict, NoReturn

import os
import gc
import re
import json
import inspect
import asyncio
import nonebot
import nonebot.permission
import nonebot.notice_request
import hoshino
from ..botmanage import group_invite

from hoshino import log, config

NAME_MODULE = __name__.split('.')[-1]

PATH_ROOT = os.path.dirname(os.path.abspath(__file__))
PATH_CONFIG = os.path.join(PATH_ROOT, f"{NAME_MODULE}.json")

_logger_name = '.'.join(__name__.split('.')[-2:])
_logger = log.new_logger(_logger_name, config.DEBUG)

invites = []

def load_config(default_value: Dict={}) -> Dict:
	if not os.path.isfile(PATH_CONFIG):
		_logger.warning(f"config file \"{PATH_CONFIG}\" not found")
		config = default_value.copy()
	else:
		with open(PATH_CONFIG, 'r') as f:
			config = json.load(f)
	config['allow_groups'] = set(config.get('allow_groups', []))
	return config

def save_config(config: Dict) -> NoReturn:
	def set_default(obj):
		if isinstance(obj, set):
			return list(obj)
		raise TypeError
	with open(PATH_CONFIG, 'w') as f:
		json.dump(config, f, default=set_default)

async def auto_reject_group_invite(session: nonebot.RequestSession, timeout: float=60*60*8) -> NoReturn:
	_logger.info(f"将在 {timeout} 秒后自动拒绝群 {session.ctx['group_id']} 的邀请")
	await asyncio.sleep(timeout)
	_logger.warning(f"处理超时，自动拒绝群 {session.ctx['group_id']} 的邀请")
	for invite in invites:
		if invite[0] == session:
			invites.remove(invite)
			break
	await session.reject(reason='管理员处理超时，邀请入群请联系维护组')
	master = hoshino.config.SUPERUSERS[0]
	msg = f"群 {session.ctx['group_id']} 的邀请处理超时，已自动拒绝"
	await nonebot.get_bot().send_private_msg(user_id=master, message=msg)

async def handle_group_invite(session: nonebot.RequestSession) -> NoReturn:
	_logger.info(f"被用户 {session.ctx['user_id']} 邀请加入群 {session.ctx['group_id']}")
	if session.ctx['user_id'] in hoshino.config.SUPERUSERS:
		_logger.info('已自动同意：管理员操作')
		await session.approve()
	else:
		config = load_config()
		allow_groups = config['allow_groups']
		if session.ctx['group_id'] in allow_groups:
			_logger.info('已自动同意：允许群列表')
			await session.approve()
		else:
			master = hoshino.config.SUPERUSERS[0]
			msg = f"被用户 {session.ctx['user_id']} 邀请加入群 {session.ctx['group_id']}\n同意群邀请 / 拒绝群邀请"
			await nonebot.get_bot().send_private_msg(user_id=master, message=msg)
			task = asyncio.create_task(auto_reject_group_invite(session))
			invites.append((session, task))

@nonebot.on_command('同意群邀请', permission=nonebot.permission.SUPERUSER, only_to_me=True)
async def approve_group_invite(session: nonebot.CommandSession) -> NoReturn:
	flag = True
	master = hoshino.config.SUPERUSERS[0]
	while invites:
		(session_invite, task) = invites.pop(0)
		if not task.done():
			flag = False
			task.cancel()
			_logger.info(f"已同意群 {session_invite.ctx['group_id']} 的邀请")
			await session_invite.approve()
			msg = f"已同意群 {session_invite.ctx['group_id']} 的邀请"
			await nonebot.get_bot().send_private_msg(user_id=master, message=msg)
			break
	if flag:
		msg = '无群邀请需要处理'
		await nonebot.get_bot().send_private_msg(user_id=master, message=msg)

@nonebot.on_command('拒绝群邀请', permission=nonebot.permission.SUPERUSER, only_to_me=True)
async def reject_group_invite(session: nonebot.CommandSession) -> NoReturn:
	flag = True
	master = hoshino.config.SUPERUSERS[0]
	while invites:
		(session_invite, task) = invites.pop(0)
		if not task.done():
			flag = False
			task.cancel()
			_logger.warning(f"已拒绝群 {session_invite.ctx['group_id']} 的邀请")
			await session_invite.reject(reason='管理员已拒绝群邀请，邀请入群请联系维护组')
			msg = f"已拒绝群 {session_invite.ctx['group_id']} 的邀请"
			await nonebot.get_bot().send_private_msg(user_id=master, message=msg)
			break
	if flag:
		msg = '无群邀请需要处理'
		await nonebot.get_bot().send_private_msg(user_id=master, message=msg)

@nonebot.on_command('待处理群邀请数', permission=nonebot.permission.SUPERUSER, only_to_me=True)
async def get_group_invite_num(session: nonebot.CommandSession) -> NoReturn:
	master = hoshino.config.SUPERUSERS[0]
	msg = f"群邀请数 {len(invites)}"
	await nonebot.get_bot().send_private_msg(user_id=master, message=msg)

@nonebot.on_command('允许加群', permission=nonebot.permission.SUPERUSER, only_to_me=True)
async def add_to_allow_groups(session: nonebot.CommandSession) -> NoReturn:
	msg = session.current_arg.strip()
	match = re.search(r'^\d+$', msg)
	if match:
		group_id = int(match.group(0))
		config = load_config()
		allow_groups = config['allow_groups']
		if group_id in allow_groups:
			await session.send(f"群 {group_id} 已存在")
		else:
			allow_groups.add(group_id)
			save_config(config)
			await session.send(f"群 {group_id} 已添加")
	else:
		await session.send('格式错误，存在非纯数字字符')

@nonebot.on_command('禁止加群', permission=nonebot.permission.SUPERUSER, only_to_me=True)
async def remove_from_allow_groups(session: nonebot.CommandSession) -> NoReturn:
	msg = session.current_arg.strip()
	match = re.search(r'^\d+$', msg)
	if match:
		group_id = int(match.group(0))
		config = load_config()
		allow_groups = config['allow_groups']
		if group_id in allow_groups:
			allow_groups.remove(group_id)
			save_config(config)
			await session.send(f"群 {group_id} 已移除")
		else:
			await session.send(f"群 {group_id} 不存在")
	else:
		await session.send('格式错误，存在非纯数字字符')

# replace ----------------------------------------------------------------------

target = group_invite.handle_group_invite
_logger.info(f"replace {target}")

for obj in gc.get_referrers(target):
	if not inspect.ismodule(obj) and obj != target:
		_logger.info(f"found {type(obj)}")
		if isinstance(obj, set):
			# request.group.invite
			obj.remove(target)
			obj.add(handle_group_invite)
			pass
		elif isinstance(obj, nonebot.notice_request.EventHandler):
			# obj.func = handle_group_invite
			pass
		else:
			pass
