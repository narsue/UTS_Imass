import json
from socket import *
from datetime import datetime
import os
import sys # For advanced error traceback
import linecache # For advanced error traceback
import traceback # For advanced error traceback
import argparse
from UTS_Imass_AI import UTS_Imass_AI
try:
    import thread #python2
    from thread import allocate_lock

except:
    import _thread as thread
    from _thread import allocate_lock

def foreced_training_time(x):
    x = int(x)
    if x < 5:
        raise argparse.ArgumentTypeError("Minimum training time is 5 minutes")
    return x


parser = argparse.ArgumentParser(description='Runs python socket server for MicroRTS AI UTS_Imass 2019')
parser.add_argument('--dir',default = None, help="Directory where the training data is stored")
parser.add_argument('--port', type=int, default=9823,help="Port for the server to host")
parser.add_argument('--force_train', type=foreced_training_time, help="Forces the agent to learn a new map for x minutes (requires --dir to be set). Min training time is 5 minutes.")
args = parser.parse_args()

def PrintException():
    exc_type, exc_value, exc_traceback = sys.exc_info()
    traceback.print_exception(exc_type, exc_value, exc_traceback,
                              limit=4, file=sys.stdout)



if args.dir is not None:
	print ('UTS_Imass Bot data Directory:',args.dir)



if args.force_train is not None:
	if args.dir is None:
		print ('UTS_Imass Bot Forced Training requires a directory please use --dir to set one'.format(args.force_train))
		exit()

	print ('UTS_Imass Bot Forced Training enabled {} minutes for new maps'.format(args.force_train))

PORT = args.port
PACKET_LENGTH = 1048576  # 1024K
BUFFER_LEN = 1048576  # 1024K
HOST_IP = '127.0.0.1'



def run_server(c, addr, server_id, pre_game_analysis_shared_memory ):
	# print ('Running new UTS_Imass game server',addr, server_id)
	pregame_len = len('preGameAnalysis')
	gameOver_len = len('gameOver')
	physical_state = None
	imass_agent = None
	packetData = c.send(bytes("UTS_Imass_Server"+"\r\n",'UTF-8'))
	reserved_json = ''
	run_server = True
	while run_server:
		try:

			data = ""
			while not data.endswith("\n"):
				data += c.recv(PACKET_LENGTH).decode("utf-8")
			# data = c.recv(1024)
			# data = data.decode(encoding='UTF-8')
		except Exception as e:
			if '[WinError 10053]' not in str(e):
				print ('UTS_Imass python bridge failed receiving data',e, server_id)
				PrintException()
			run_server = False

		msg = "ack"
		# print (data)
		if data[:9] == 'getAction':
			# if reserved_json:
			reserved_json += data

			data = reserved_json
			reserved_json = ''
			try:
				# print('start')
				frame_start = datetime.now()

				json_index = data.index('\n')
				gs = json.loads(data[json_index+1:])
				my_player_id = int(data[10:json_index])
				msg = imass_agent.forward(gs, my_player_id)
				msg = json.dumps(msg)
				# print('end')

				frame_duration = (datetime.now()-frame_start).total_seconds()
				if frame_duration > 0.095: # should remain under 100 ms
					print ('Warning FrameTime Seconds:{}'.format(frame_duration), server_id)
			except Exception as e:
				print ("UTS_Imass python bridge failed to convert getAction to json. Error:",e, server_id)
				PrintException()
				run_server = False

			# msg = "[]"
		elif data[:pregame_len] == 'preGameAnalysis':
			try:
				reserved_json += data
	
				data = reserved_json
				reserved_json = ''
				data_elements = data.split()
				time_limit = int(data_elements[1])
				read_write_directory = data_elements[2] # Gets a directory in tournament mode 
				if read_write_directory[0] =='{': # no directory was given this is the json data
					read_write_directory = None
				json_index = data.index('\n')
				gs = json.loads(data[json_index+1:])
				imass_agent.pre_game_analysis(time_limit, read_write_directory, gs)

			except Exception as e:
				print ("UTS_Imass python bridge process preGameAnalysis message. Error:",e, server_id)
				PrintException()
				run_server = False

		elif data[:gameOver_len] == 'gameOver':
			try:
				winner_id = int(data.split()[1])
				imass_agent.backward(winner_id)
				c.send(bytes('ack\n','UTF-8'))
			except Exception as e:
				print ("UTS_Imass python bridge process preGameAnalysis message. Error:",e, server_id)
				PrintException()

			run_server = False


		elif data[:3] == 'utt':
			try:
				reserved_json += data
				data = reserved_json
				reserved_json = ''
				if imass_agent is None:
					physical_state = json.loads(data[4:])
					imass_agent = UTS_Imass_AI(physical_state, server_id, pre_game_analysis_shared_memory)
			except Exception as e:
				print ("UTS_Imass python bridge failed to utt contructor message to json. Error:",e, server_id)
				PrintException()
				run_server = False
		elif data[:5] == 'slave':
			imass_agent.set_slave_mode()

		if run_server: 
			try:
				c.send(bytes(msg+'\n','UTF-8'))
				# print ('Sent', msg)
			except Exception as e:
				# print ('UTS_Imass python bridge failed to send data',e)
				# PrintException()
				run_server = False

	c.close()	
	# print ('Server closed',server_id)

masterSocket=socket(AF_INET, SOCK_STREAM)
masterSocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
masterSocket.setsockopt(SOL_SOCKET,SO_RCVBUF,BUFFER_LEN)
# masterSocket.settimeout(15)
masterSocket.bind((HOST_IP, PORT))
# masterSocket.setblocking(0)
print("UTS_Imass Server Listening on IP:{} Port:{}".format(HOST_IP, PORT))
server_id = 0
pre_game_analysis_shared_memory = {'sharing_enabled':False,'log_directory':None,'manual_directory':args.dir,'force_train':args.force_train}

if args.dir is not None: 
	# Check if the directory exists. If not attempt to create it
	if not os.path.isdir(args.dir):
		try:
			os.makedirs(args.dir)
			print ('Created data directory {} as it did not exist'.format(args.dir))
		except Exception as e:
			print ("Error UTS_Imass Server attempting to create data directory failed")
			print (e)
			exit()
while 1:
	try:
		masterSocket.listen(25)
		c, addr = masterSocket.accept()  
		thread.start_new_thread( run_server, (c, addr, server_id, pre_game_analysis_shared_memory) )
		server_id += 1
	except Exception as e:
		print ("Exception occured",e)