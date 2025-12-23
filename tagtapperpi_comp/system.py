import asyncio

async def reboot():
    await asyncio.create_subprocess_exec("sudo", "reboot")

async def poweroff():
    await asyncio.create_subprocess_exec("sudo", "poweroff")
