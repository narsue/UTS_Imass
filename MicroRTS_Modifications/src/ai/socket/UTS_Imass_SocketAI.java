/*
 * To change this license header, choose License Headers in Project Properties.
 * To change this template file, choose Tools | Templates
 * and open the template in the editor.
 */
package ai.socket;

import ai.core.AI;
import ai.core.AIWithComputationBudget;
import ai.core.ParameterSpecification;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.io.StringReader;
import java.net.Socket;
import java.util.ArrayList;
import java.util.List;
import org.jdom.Element;
import org.jdom.input.SAXBuilder;
import rts.GameState;
import rts.PlayerAction;
import rts.units.UnitTypeTable;
import util.XMLWriter;

/**
 *
 * @author santi
 */
public class UTS_Imass_SocketAI extends AIWithComputationBudget {
    public static int DEBUG = 0;
    
    public static final int LANGUAGE_XML = 1;
    public static final int LANGUAGE_JSON = 2;
    
    UnitTypeTable utt = null;
            
    int communication_language = LANGUAGE_JSON;
    String serverAddress = "127.0.0.1";
    int serverPort = 9823;
    Socket socket = null;
    BufferedReader in_pipe = null;
    PrintWriter out_pipe = null;
    Boolean connecting = false;
    
    public UTS_Imass_SocketAI(UnitTypeTable a_utt) {
        super(100,-1);
        utt = a_utt;
        try {
            connectToServer();
        }catch(Exception e) {
            e.printStackTrace();
        }
    }
    
        
    public UTS_Imass_SocketAI(int mt, int mi, String a_sa, int a_port, int a_language, UnitTypeTable a_utt) {
        super(mt, mi);
        serverAddress = a_sa;
        serverPort = a_port;
        communication_language = a_language;
        utt = a_utt;
        try {
            connectToServer();
        }catch(Exception e) {
            e.printStackTrace();
        }
    }
//
//    private UTS_Imass_SocketAI(int mt, int mi, UnitTypeTable a_utt, int a_language, Socket socket) {
//        super(mt, mi);
//        communication_language = a_language;
//        utt = a_utt;
//        try {
//            this.socket = socket;
//            in_pipe = new BufferedReader(new InputStreamReader(socket.getInputStream()));
//            out_pipe = new PrintWriter(socket.getOutputStream(), true);
//
//            // Consume the initial welcoming messages from the server
//            while(!in_pipe.ready());
//            while(in_pipe.ready()) in_pipe.readLine();
//
//            if (DEBUG>=1) System.out.println("SocketAI: welcome message received");
//            reset();
//        }catch(Exception e) {
//            e.printStackTrace();
//        }
//    }

    /**
     * Creates a SocketAI from an existing socket.
     * @param mt The time budget in milliseconds.
     * @param mi The iterations budget in milliseconds
     * @param a_utt The unit type table.
     * @param a_language The communication layer to use.
     * @param socket The socket the ai will communicate over.
     */
//    public static UTS_Imass_SocketAI createFromExistingSocket(int mt, int mi, UnitTypeTable a_utt, int a_language, Socket socket) {
//        return new UTS_Imass_SocketAI(mt, mi, a_utt, a_language, socket);
//    }
//    
    
    public void connectToServer() throws Exception {
        // Make connection and initialize streams
        connecting = true;

        socket = new Socket(serverAddress, serverPort);
        in_pipe = new BufferedReader(new InputStreamReader(socket.getInputStream()));
        out_pipe = new PrintWriter(socket.getOutputStream(), true);
        // Consume the initial welcoming messages from the server
        while(!in_pipe.ready());
        while(in_pipe.ready()) in_pipe.readLine();

        if (DEBUG>=1) System.out.println("SocketAI: welcome message received");
        connecting = false;

        reset();
    }
    
    
    @Override
    public void reset() {
        try {
            // set the game parameters:
            out_pipe.append("budget " + TIME_BUDGET + " " + ITERATIONS_BUDGET + "\n");
            out_pipe.flush();

            if (DEBUG>=1) System.out.println("SocketAI: budgetd sent, waiting for ack");
            
            // wait for ack:
            in_pipe.readLine();
            while(in_pipe.ready()) in_pipe.readLine();

            if (DEBUG>=1) System.out.println("SocketAI: ack received");

            // send the utt:
            out_pipe.append("utt\n");
            if (communication_language == LANGUAGE_XML) {
                XMLWriter w = new XMLWriter(out_pipe, " ");
                utt.toxml(w);
                w.flush();
                out_pipe.append("\n");
                out_pipe.flush();                
            } else if (communication_language == LANGUAGE_JSON) {
                utt.toJSON(out_pipe);
                out_pipe.append("\n");
                out_pipe.flush();
            } else {
                throw new Exception("Communication language " + communication_language + " not supported!");
            }
            if (DEBUG>=1) System.out.println("SocketAI: UTT sent, waiting for ack");
            
            // wait for ack:
            in_pipe.readLine();
            
            // read any extra left-over lines
            while(in_pipe.ready()) in_pipe.readLine();
            if (DEBUG>=1) System.out.println("SocketAI: ack received");

        }catch(Exception e) {
            e.printStackTrace();
        }
    }
    
    private Boolean reconnect()
    {
        try {
            connectToServer();
            return true;
        }catch(Exception e) {
            connecting = false;
            e.printStackTrace();
        }
        return false;
    }

    @Override
    public PlayerAction getAction(int player, GameState gs) throws Exception {
        // send the game state:
        out_pipe.append("getAction " + player + "\n");
        
        gs.toJSON(out_pipe);
        out_pipe.append("\n");
        out_pipe.flush();

        // parse the action:
        long start = System.currentTimeMillis();
        // In case of timeouts due to other agents we may need to reconnect to server
        String actionString = "[]";
        try {
            actionString = in_pipe.readLine();
            PlayerAction pa = PlayerAction.fromJSON(actionString, gs, utt);
            pa.fillWithNones(gs, player, 1);
            long dt = (System.currentTimeMillis()-start);
            if (dt>80)
             System.out.println("Update dt: " + Long.toString(dt));
            
            return pa;
        }catch(Exception e) {
//            e.printStackTrace();
              if (connecting == false && reconnect())
                return getAction(player, gs);
              else
              {
                PlayerAction pa = PlayerAction.fromJSON("[]", gs, utt);
                pa.fillWithNones(gs, player, 1);
                
                long dt = (System.currentTimeMillis()-start);
                if (dt>80)
                 System.out.println("Update dt: " + Long.toString(dt));
                return pa;
              }
              
        }
       
        // System.out.println("action received from server: " + actionString);

       
    }


    @Override
    public void preGameAnalysis(GameState gs, long milliseconds) throws Exception 
    {
        // send the game state:
        out_pipe.append("preGameAnalysis " + milliseconds + "\n");

        gs.toJSON(out_pipe);
        out_pipe.append("\n");
        out_pipe.flush();
        // wait for ack:
        try {
            in_pipe.readLine();
            
        }catch(Exception e) {
//            e.printStackTrace();
              if (connecting == false && reconnect())
                preGameAnalysis(gs, milliseconds);
        }
         
    }

    
    @Override
    public void preGameAnalysis(GameState gs, long milliseconds, String readWriteFolder) throws Exception 
    {
        // send the game state:
        out_pipe.append("preGameAnalysis " + milliseconds + "  \""+System.getProperty("user.dir")+"\\"+readWriteFolder+"\"\n");

        gs.toJSON(out_pipe);
        out_pipe.append("\n");
        out_pipe.flush();
        // wait for ack:
        try {
            in_pipe.readLine();
            
        }catch(Exception e) {
//            e.printStackTrace();
              if (connecting == false && reconnect())
                preGameAnalysis(gs, milliseconds, readWriteFolder);
              
        }
             
    }
    
    
    @Override
    public void gameOver(int winner) throws Exception
    {
        // send the game state:
        out_pipe.append("gameOver " + winner + "\n");
        out_pipe.flush();
                
        // wait for ack:
        in_pipe.readLine();
    }
    
    
    @Override
    public AI clone() {
        return new UTS_Imass_SocketAI(TIME_BUDGET, ITERATIONS_BUDGET, serverAddress, serverPort, communication_language, utt);
    }
    

    @Override
    public List<ParameterSpecification> getParameters() {
        List<ParameterSpecification> l = new ArrayList<>();
//        
//        l.add(new ParameterSpecification("Server Address", String.class, "127.0.0.1"));
//        l.add(new ParameterSpecification("Server Port", Integer.class, 9823));
//        l.add(new ParameterSpecification("Language", Integer.class, LANGUAGE_XML));
        
        return l;
    }
}
