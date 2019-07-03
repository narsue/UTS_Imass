# UTS Imass Bot

A Python bot written for the MicroRTS tournament.

For ease of installation several binary files were included in the repository.
Which include a slightly modified copy (see java files in Remote_MicroRTS_Java for changes).
The microrts jar is required so that the agent can perform self play as part of the pre-game-analysis.

Requires Python 3.6.


To run:
`python UTS_Imass_Server.py <path/to/tournament>`

where `<path/to/tournament>` is the folder holding the `readWriteFolder` location passed in the preGameAnalysis step, as the `readWriteFolder` is relative but `UTS_Imass_Server` needs to run in it's own folder.

Uses port 9823 and JSON for socket communication.

# Requirements

Requires a C++ library which is included as Python bindings for both Windows and Ubuntu. If this does not work, the library source can be retrieved [here](https://github.com/narsue/BLJPS_Python) and built with CMake.

# Basic usage for demonstrations

1. Download MicroRTS https://github.com/santiontanon/microrts
2. Download UTS_Imass repo from this website https://github.com/narsue/UTS_Imass
3. Copy files from MicroRTS_Modifications/src into the MicroRTS/src
4. Using a java based IDE such as Netbeans create a new project for MicroRTS
5. Add the src folder within MicroRTS as the source directory
6. Add the libraries within MicroRTS/lib to the project
7. Run the java file src/gui/frontend/FrontEnd.java (You should now get a GUI of the game popup)
8. Open a terminal window or IDE within the UTS_Imass/UTS_Imass_2019_Server directory
9. Using python3.6 run 'python UTS_Imass_Server.py --dir training_data --force_train 5'
This will run the server and any new maps that the bot hasn't seen will be trained on for 5 minutes
The training data will be stored in the local folder UTS_Imass/UTS_Imass_2019_Server directory/training_data
10. Within the MicroRTS GUI in Player 1 click the drop down and select UTS_Imass_SocketAI
11. Click Start on the GUI
12. In the UTS_Imass_Server terminal output you should see something like below where it gives training progress updates.
Now running self learning on precompiled micro rts
UTS_Imass beginning self training. This will run for the specified time given 5.00 minutes
Training ... 0.0sec 0.0%
Training ... 0.8sec 0.3%
Current best config is: (1, 0, 200, ()) [1.0, 2, 2]
13. After 5 minutes the training has completed and the visualisation will playout the game
14. You can change to any other map or opponent to play against (Any new maps will incur the training process)


# Tournament usage

Confirm the steps for demonstrations are successful before attempting a competition
A competition differs from the previous instructions as MicroRTS provides the UTS_Imass_Server with a directory and training timebudget (in milliseconds)

1. For this case you can choose if you want the UTS_Imass agent to use a directory of your choice (use --dir) or the tournament directories (do not use --dir)
2. It is best to not use the --force_train arguement with tournament settings as the tournament should dictate the amount of time each AI gets to spend on training. Defining a value for --force_train may cause the bot to train for long and get disqualified due to exceeding time constraints
3. It is best to use the provided UTS_Imass_SocketAI to play in the tournament as it has been slightly modified relative to the SocketAI version. Basic changes like providing the tournament directory as an absolute path instead of a relative path. 