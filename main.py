from multiprocessing import Process
import asyncio
import requests
import json
import discord
import sys
import PySimpleGUI as sg
import os
import gspread
from datetime import datetime
import webbrowser



#GLOBAL VARIABLES

isRunning = False
alertFlag = True

#CREATING PERSISTANT SETTINGS FILE
INI_PATH = os.path.join(os.path.dirname(__file__), "data", f'ini.json')
STATS_PATH = os.path.join(os.path.dirname(__file__), "data", f'stats.json')
ICON_PATH = os.path.join(os.path.dirname(__file__), "data", f'favicon.ico')
ini_values = None
try:
  with open(INI_PATH, "r") as f:
    ini_values = json.load(f)
except:
  ini_values = dict()
  ini_values["token"] = ""
  ini_values["minerid"] = ""
  ini_values["channelname"] = "general"
  ini_values["delay"] = 60
  ini_values["awthreshold"] = 1
  ini_values["hrmin"] = 100
  ini_values["hrmax"] = 300
  ini_values["email"] = ""
  ini_values["sheetlink"] = ""
  with open(INI_PATH, "w") as f:
    json.dump(ini_values, f)




#DISCORD BOT LOOP, THREADING ONLY --------------------------------------------------------------------------------

client = discord.Client()
embed = discord.Embed()

# 1. Monitor whether or not you are live
# 2. Monitor changing hash rates beyond a certain threshold
# 3. Monitor daily payouts
# 4. Send a discord message for the above updates

def get_creds():
  response = requests.get("https://heyer.app/acb").json()
  return response

async def remake_sheet():
  with open(INI_PATH, "r") as f:
    ini_values = json.load(f)
  gc = gspread.service_account_from_dict(get_creds())
  
  sh = gc.open(f'{ini_values["email"]}\'s Crypto Bot Monitor')
  worksheet = sh.worksheet("EtherMine Daily Payouts")
  sh.del_worksheet(worksheet)
  await chkpay(f"https://api.ethermine.org/miner/:{ini_values['minerid']}/payouts")


async def chkpay(url):
  with open(INI_PATH, "r") as f:
    ini_values = json.load(f)
  gc = gspread.service_account_from_dict(get_creds())

  try:
      sh = gc.open(f'{ini_values["email"]}\'s Crypto Bot Monitor')
      worksheet = sh.worksheet("EtherMine Daily Payouts")
  except:
      sh = gc.create(f'{ini_values["email"]}\'s Crypto Bot Monitor')
      sh.share(ini_values["email"], perm_type='user', role='writer')
      worksheet = sh.add_worksheet(title="EtherMine Daily Payouts", rows="100", cols="2", index = 0)
      worksheet.update(f"A1", "TIME OF PAYMENT")
      worksheet.update(f"B1", "AMOUNT (E)")
      worksheet.format('A1:B1', {'textFormat': {'bold': True}})
      worksheet.columns_auto_resize(0, 2)
  
  ini_values["sheetlink"] = sh.url

  with open(INI_PATH, "w") as fw:
    json.dump(ini_values, fw)

  response = requests.get(url).json()

  list_of_lists = worksheet.get_values()
  for x in range(len(list_of_lists)):
    if x != 0:
      list_of_lists[x][1] = float(list_of_lists[x][1])

  update_msg = ""

  for i in response["data"]:
      entry = []
      entry.append(datetime.utcfromtimestamp(i["paidOn"]).strftime('%Y-%m-%d %H:%M:%S'))
      entry.append(round(i["amount"]*0.000000000000000001, 6))
      if entry not in list_of_lists:
          update_msg += f"PAYMENT HAS ARRIVED\n`Time:{entry[0]}, Amount:{entry[1]}`\n"
          list_of_lists.append(entry)

  worksheet.update("A1", list_of_lists)

  if update_msg != "":
    await broadcast(client, update_msg)


async def chklive(url):
  response = requests.get(url).json()
  with open(INI_PATH, "r") as f:
    ini_values = json.load(f)
  data = response["data"]
  with open(STATS_PATH, "w") as f:
    json.dump(data, f)
  if data["activeWorkers"] < ini_values["awthreshold"] and alertFlag:
    await broadcast(client, f"ALERT: ACTIVE WORKERS BELOW SPECIFIED THRESHOLD.\nCURRENTLY ACTIVE: {data['activeWorkers']}\nMINIMUM THRESHOLD: {ini_values['awthreshold']}")
  if data["currentHashrate"]/1000000 < ini_values["hrmin"] and alertFlag:
    await broadcast(client, f"ALERT: HASHRATE IS CURRENTLY BELOW THE SPECIFIED THRESHOLD.\nCURRENT HASHRATE: {data['currentHashrate']/1000000} MH/s\nMINIMUM THRESHOLD: {ini_values['hrmin']} MH/s")
  if data["currentHashrate"]/1000000 > ini_values["hrmax"] and alertFlag:
    await broadcast(client, f"ALERT: HASHRATE IS CURRENTLY ABOVE THE SPECIFIED THRESHOLD.\nCURRENT HASHRATE: {data['currentHashrate']/1000000} MH/s\nMAXIMUM THRESHOLD: {ini_values['hrmax']} MH/s")

async def broadcast(cli, msg):
  for server in cli.guilds:
      for channel in server.channels:
          if str(channel.type) == 'text':
              if ini_values["channelname"] == "" or ini_values["channelname"] == "general":
                if channel.name == "general":
                  try:
                      await channel.send(msg)
                  except:
                      continue
              elif channel.name == ini_values["channelname"]:
                try:
                    await channel.send(msg)
                except:
                    continue

async def direct_msg(cli, channel, msg):
  channel = cli.get_channel(channel)
  await channel.send(msg)

def get_delay():
    with open(INI_PATH, "r") as f:
      ini_values = json.load(f)
      return ini_values["delay"]



def get_full_day_delay():
  return 86400

async def repeat_task(task, arg, delay):
    while True:
        await task(arg)
        await asyncio.sleep(delay())

async def get_stats(channel):
    if os.path.exists(STATS_PATH):
      msg = ""
      with open(STATS_PATH, "r") as f:
        stats = json.load(f)
        for x, y in stats.items():
          msg += f"`{x}` : `{y}`\n"
      await channel.send(msg)
    else:
      await channel.send("NO STATS CURRENTLY AVAILABLE")

@client.event
async def on_ready():
  print("Bot is ready to party, logged in as {0.user}.".format(client))
  client.loop.create_task(repeat_task(chklive, f"https://api.ethermine.org/miner/:{ini_values['minerid']}/currentStats", get_delay))
  client.loop.create_task(repeat_task(chkpay, f"https://api.ethermine.org/miner/:{ini_values['minerid']}/payouts", get_full_day_delay))

@client.event
async def on_message(message):
  global alertFlag
  if message.author == client.user:
    return
  elif message.content.lower() == ("!stop"):
      await message.channel.send(f"Alerts muted")
      alertFlag = False
  elif message.content.lower() == ("!start"):
      await message.channel.send(f"Alerts unmuted")
      alertFlag = True
  elif message.content.lower() == ("!stats"):
      await get_stats(message.channel)
  else:
    return   

def runbot():
  global isRunning
  isRunning = True
  with open(INI_PATH, "r") as f:
    ini_values = json.load(f)
    client.run(ini_values["token"])

def start_proc():
  proc = Process(target = runbot, name = "runbot")
  proc.start()
  return proc

def proc_stop(proc_to_stop):
  proc_to_stop.terminate()

def proc_remake():
  asyncio.run(remake_sheet())

if __name__ == '__main__':

  #GUI LOOP --------------------------------------------------------------------------------
  
  sg.theme('DarkGray13')
  
  def go_to_sheet():
    with open(INI_PATH, "r") as f:
      ini_values = json.load(f)
    if ini_values["sheetlink"] == "":
      print("NO SPREADSHEET CREATED YET, RUN BOT FIRST")
    else:
      webbrowser.open(ini_values["sheetlink"], new=2)
  
  def check_values():
    if ini_values["token"] == "" or ini_values["minerid"] == "" or ini_values["email"] == "":
      return False
    else:
      return True

  def make_primary_win():
    layout = [
        [sg.Text('DISCORD API TOKEN*:'), sg.Input(ini_values["token"], expand_x= True, key='apiin', tooltip = "Available at https://discord.com/developers/applications")],
        [sg.Text('DISCORD CHANNEL NAME: '), sg.Input(ini_values["channelname"], expand_x= True, key='chin', tooltip = "Defaults to general chat channel in whichever servers it's in. Change to a specific channel name to broadcast to only that channel.")],
        [sg.Text('MINER ID*:'), sg.Input(ini_values["minerid"], expand_x= True, key='midin', tooltip = "Ethermine Only")],
        [sg.Text('EMAIL (FOR G-API)*:'), sg.Input(ini_values["email"], expand_x= True, key='emailin', tooltip = "New sheet created upon email change, check your inbox for share request."), sg.Button('Open', key = "opensheet"), sg.Button('Remake', key = "remakesheet")],
        [sg.Text('CHECK INTERVAL (SECONDS):'), sg.Spin(list(range(30,86400)), initial_value = ini_values["delay"], key='delay', tooltip = "Defaults to 60 seconds, max delay of 86400 (1 Day)")],
        [sg.Text('ACTIVE WORKER THRESHOLD:'), sg.Spin(list(range(1,99)), initial_value = ini_values["awthreshold"], key='awt', tooltip = "Defaults to 1 Worker")],
        [sg.Text('HASH RATE THRESHOLD:'), sg.Spin(list(range(0,99999)), initial_value = ini_values["hrmin"], key='hrmin', tooltip = "Minimum Hash Rate"), sg.Text('Min (MH/s)'),sg.Spin(list(range(0,99999)), initial_value = ini_values["hrmax"], key='hrmax', tooltip = "Maximum Hash Rate"), sg.Text('Max (MH/s)')],
        [sg.Button('Save Configuration', key = "submitapi")],
        [sg.Multiline(size=(75, 6),
                      disabled = True,
                      auto_refresh = True,
                      reroute_stdout = True,
                      reroute_stderr= True,
                      reroute_cprint= True,
                      autoscroll=True)],
        [sg.Button('Start Bot', key = "Start"), sg.Button('Stop Bot', key = "Stop"), sg.Button('Stats', key = "stats"), sg.Button('Commands', key = "cmd"), sg.Exit()],
    ]

    return sg.Window('Austin\'s Crypto Miner Monitor', layout, icon = ICON_PATH)

  def make_secondary_win():
    statstr = ""
    if os.path.exists(STATS_PATH):
      with open(STATS_PATH, "r") as f:
        stats = json.load(f)
        for x, y in stats.items():
          statstr += (f"{x} : {y}\n\n")
    return statstr
  
  def make_tertiary_win():
    prompt = "!stop - Mutes all alerts\n\n!start - Unmutes all alerts\n\n!stats - Sends miner's current status via discord message\n\n"
    return prompt

  def main():
    
    global isRunning
    primary, secondary = make_primary_win(), None        # start off with 1 window open
    primary.finalize()
    current_bot = None
    while True:             # Event Loop
        window, event, values = sg.read_all_windows(timeout=100)
        if event in (sg.WIN_CLOSED, 'Exit'):
            window.close()
            if window == secondary:
              secondary = None
            elif window == primary:
              if current_bot:
                proc_stop(current_bot)
              break
        elif event == "submitapi":
          ini_values["token"] = values["apiin"]
          ini_values["minerid"] = values["midin"]
          ini_values["channelname"] = values["chin"]
          ini_values["email"] = values["emailin"]
          ini_values["delay"] = int(values["delay"])
          ini_values["awthreshold"] = int(values["awt"])
          ini_values["hrmin"] = int(values["hrmin"])
          ini_values["hrmax"] = int(values["hrmax"])
          with open(INI_PATH, "w") as f:
            json.dump(ini_values, f)
        elif event == 'stats':
          if isRunning == True:
            sg.popup(make_secondary_win(), title = "~ STATS ~", )
          else:
            print("BOT ISN'T RUNNING, START BOT TO VIEW STATS")
        elif event == 'cmd':
          sg.popup(make_tertiary_win(), title = "~ DISCORD COMMANDS ~", )
        elif event == 'Start':
            if isRunning == True:
              print("BOT IS ALREADY RUNNING")
            elif check_values():       
              current_bot = start_proc()
              print("STARTING BOT")
              isRunning = True
            else:
              print("MISSING CONFIG VALUES")
        elif event == 'Stop':
            if isRunning == True:
              print("STOPPING BOT")
              isRunning = False
              proc_stop(current_bot)
            else:
              print("NO BOTS ARE RUNNING")
        elif event == 'opensheet':
          if (ini_values["sheetlink"]) == "":
            print("START BOT FIRST TO MAKE SPREADSHEET. IF STILL UNRESPONSIVE, RESTART PROGRAM.")
          else:     
            go_to_sheet()
        elif event == 'remakesheet':
          if isRunning:
            print("REMAKING SPREADSHEET. WAIT FOR EMAIL CONFIRMATION")
            proc = Process(target = proc_remake, name = "proc_remake")
            proc.start()
          else:
            print("START BOT BEFORE ATTEMPTING TO REMAKE SPREADSHEET")

    window.close()
    sys.exit()
  
  
  main()

