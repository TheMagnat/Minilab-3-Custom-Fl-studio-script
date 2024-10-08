"""
[[
	Surface:	MiniLab3
	Developer:	Farès MEZDOUR
	Version:	1.0.1

    Copyright (c) 2022 Farès MEZDOUR
]]
"""

import channels
import mixer
import patterns
import transport
import ui
import device
import plugins
import midi
import general
import MiniLab3Plugin


from MiniLab3Dispatch import MidiEventDispatcher
from MiniLab3Dispatch import send_to_device
from MiniLab3Display import MiniLabDisplay
from MiniLab3Pages import MiniLabPagedDisplay
from MiniLab3Navigation import NavigationMode
from MiniLab3Plugin import KNOB_HW_VALUE
import ArturiaVCOL

from KeyScaler import KeyScaler


# This class processes all CC coming from the controller
# The class creates new handler for each function
# The class calls the right fonction depending on the incoming CC


## CONSTANT


PORT_MIDICC_ANALOGLAB = 10
WidMixer = 0
WidChannelRack = 1
WidPlaylist = 2
WidBrowser = 4
WidPlugin = 5


# Event code indicating stop event
SS_STOP = 0

# Event code indicating start start event
SS_START = 2

ANALOGLAB_KNOB_ID = (
                    9,
                    16,
                    17,
                    18,
                    19,
                    71,
                    74,
                    76,
                    77,
                    82,
                    83,
                    85,
                    93,
                    112,
                    113,
                    114,
                    115,
                    )

KNOB_ID = (
            86,
            87,
            89,
            90,
            110,
            111,
            116,
            117
            )

PAD_MATRIX = [
        0x34, 0x35, 0x36, 0x37,
        0x38, 0x39, 0x3A, 0x3B,
        0x44, 0x45, 0x46, 0x47,
        0x48, 0x49, 0x4A, 0x4B
]

PAD_MATRIX_STATE = [
        0, 0, 0, 0,
        0, 0, 0, 0,
        0, 0, 0, 0,
        0, 0, 0, 0
]

# FPC MAP
FPC_MAP = {
            "36":37,
            "37":36,
            "38":42,
            "39":54,
            "40":40,
            "41":38,
            "42":46,
            "43":44,
            
            "44":48,
            "45":47,
            "46":45,
            "47":43,
            "48":49,
            "49":55,
            "50":51,
            "51":53
            }
            
# KNOB HW VALUE
KNOB_HW_ID = [
            0x07,
            0x08,
            0x09,
            0x0A,
            0x0B,
            0x0C,
            0x0D,
            0x0E,
            ]
            
# UPDATE KNOBS
UPDATE_KNOB = 0

class MiniLabMidiProcessor:
    @staticmethod
    def _is_pressed(event):
        return event.controlVal != 0

    def __init__(self, mk3):
        
        self.shift = False
        
        # Snap to scale
        self.keyScaler = KeyScaler()
        self.snapToScale = False
        self.snapToScaleJustEdited = False
        self.snapToScaleUnderPressure = False
        
        def by_midi_id(event) : return event.midiId
        def by_control_num(event) : return event.controlNum
        def by_velocity(event) : return event.data2
        def by_status(event) : return event.status
        def by_sysex(event) : return event.sysex
        def ignore_release(event): return self._is_pressed(event)
        def ignore_press(event): return not self._is_pressed(event)
        def is_drum(event): return event.status in [153, 137]

        self._mk3 = mk3

        # Main event, will then dispatch to other Dispatcher
        self._midi_id_dispatcher = (
            MidiEventDispatcher(by_midi_id)
            .NewHandler(176, self.OnCommandEvent)
            .NewHandler(224, self.OnWheelEvent)
            
            # Drum event
            .NewHandler(144, self.onMidiEvent) # Pressed
            .NewHandler(128, self.onMidiEvent) # Released
            )
        
        self._sysex_dispatcher = (
            MidiEventDispatcher(by_sysex)
            .NewHandler(b'\xf0\x00 k\x7fB\x02\x00@b\x01\xf7', self.ArturiaMemory, ignore_release)
            .NewHandler(b'\xf0\x00 k\x7fB\x02\x00@b\x02\xf7', self.DAWMemory, ignore_release)
            )
        
        # Drum pad
        self._midi_drum_pad_dispatcher = (
            MidiEventDispatcher(by_control_num)
            .NewHandler(36, self.SnapToScale)
            .NewHandler(37, self.WaitForInput, ignore_release)
            .NewHandler(38, self.StepByStep, ignore_release)
            .NewHandler(39, self.Loop, ignore_release)
            .NewHandler(40, self.Stop)
            .NewHandler(41, self.Start, ignore_release)
            .NewHandler(42, self.Record, ignore_release)
            .NewHandler(43, self.Undo) # Drum  8 (Tap)
        )

        self._midi_command_dispatcher = (
            MidiEventDispatcher(by_control_num)
            
            # MAPPING PAD
            
            .NewHandler(107, self.Start, ignore_press)
            .NewHandler(106, self.Stop)
            .NewHandler(108, self.Record, ignore_press)
            .NewHandler(109, self.Redo)
            .NewHandler(102, self.SetClick, ignore_press)
            .NewHandler(105, self.Loop, ignore_press)
            .NewHandler(103, self.Rewind)
            .NewHandler(104, self.FastForward)
            .NewHandler(118, self.SwitchWindow, ignore_release)
            .NewHandler(28, self.OnKnobEvent)
            .NewHandler(29, self.PluginTest)
            #.NewHandler(29, self.AllLEDs, ignore_release)
            .NewHandler(119, self.ToggleBrowserChannelRack, ignore_release)
            .NewHandler(27, self.ShiftOn)
            
            
            # MAPPING KNOBS
            
            .NewHandler(14, self.SetVolumeTrack)
            .NewHandler(31, self.SetPanTrack)
            .NewHandlerForKeys(ANALOGLAB_KNOB_ID, self.ForwardAnalogLab)
            .NewHandlerForKeys(KNOB_ID, self.Plugin)
            .NewHandler(1, self.ForwardAnalogLab)
            .NewHandler(15, self.Plugin)
            .NewHandler(30, self.Plugin)
            
            
        )
        
        self._knob_dispatcher = (
            MidiEventDispatcher(by_velocity)
            .NewHandlerForKeys(range(65,73), self.Navigator)
            .NewHandlerForKeys(range(55,63), self.Navigator)
        )
        
        # MAPPING WHEEL
        self._wheel_dispatcher = (
            MidiEventDispatcher(by_status)
        )
        
        #~NAVIGATION
        self._navigation = NavigationMode(self._mk3.paged_display())


    # DISPATCH
    def ProcessEvent(self, event) :
        # print("DEBUG PRINT: ", "MidiId: ", event.midiId, "controlNum: ", event.controlNum, "data1: ", event.data1, "data2: ", event.data2, "status: ", event.status, "sysex: ", event.sysex, "controlVal: ", event.controlVal)
        return self._midi_id_dispatcher.Dispatch(event)

    def onMidiEvent(self, event):
        # On drum event
        if event.status in [153, 137]:
            return self._midi_drum_pad_dispatcher.Dispatch(event)

        if self.snapToScaleUnderPressure:
            newNote = self.keyScaler.getEventNote(event)
            self.keyScaler.setRootNote(newNote)
            self._navigation.SnapRefresh(self.keyScaler.getCurrentScaleName())
            self.snapToScaleJustEdited = True

        elif self.snapToScale:
            self.keyScaler.scaleEvent(event)

        return False

    def OnCommandEvent(self, event):
        return self._midi_command_dispatcher.Dispatch(event)

    def OnWheelEvent(self, event):
        return self._wheel_dispatcher.Dispatch(event)

    def OnKnobEvent(self, event):
        return self._knob_dispatcher.Dispatch(event)

    # def OnDrumEvent(self, event) :
    #     index = event.data1
    #     if event.status == 153 :
    #         self.PadOn(index)
    #         event.data1 = FPC_MAP.get(str(event.data1))
    #     elif event.status == 137 : 
    #         self.PadOff(index)
    #         event.data1 = FPC_MAP.get(str(event.data1))
    #     event.handled = False

    # WINDOW



    def _show_and_focus(self, window):
        if not ui.getVisible(window):
            ui.showWindow(window)
        if not ui.getFocused(window):
            ui.setFocused(window)
  
  
    def _hideAll(self, event) :
        for i in range (channels.channelCount()) :
            channels.showEditor(i,0)


    def SwitchWindow(self, event) :
        if ui.getFocused(WidChannelRack) :
            self.showPlugin(event)
        elif ui.getFocused(WidPlugin) :
            self.showPlugin(event)
        elif ui.getFocused(WidMixer) :
            mixer.armTrack(mixer.trackNumber())
            #plugin = channels.selectedChannel()
            # for i in range(plugins.getParamCount(plugin)) :
                # print(i, plugins.getPluginName(channels.selectedChannel()),plugins.getParamName(i,plugin), plugins.getParamValue(i,plugin))
            #self.GetConnexionMessage()
        elif ui.getFocused(WidBrowser) :
            nodeFileType = ui.getFocusedNodeFileType()
            if nodeFileType == -1:
                return
            if nodeFileType <= -100:
                transport.globalTransport(midi.FPT_Enter, 1)
            else:
                ui.selectBrowserMenuItem()
                if not ui.isInPopupMenu() :
                    self._navigation.PressRefresh()
                else :
                    transport.globalTransport(midi.FPT_No, 1)
                    self._show_and_focus(WidPlugin)

        return True

    # NAVIGATION



    def ToggleBrowserChannelRack(self, event) :
        if ui.getFocused(WidBrowser) != True :
            self._hideAll(event)
            self._show_and_focus(WidBrowser)
            self._navigation.BrowserRefresh()
        else :
            self._hideAll(event)
            self._show_and_focus(WidChannelRack)
            self._navigation.ChannelRackRefresh()
        return True
            
    def TogglePlaylistChannelRack(self, event) :
        if ui.getFocused(WidPlaylist) != True :
            self._hideAll(event)
            self._show_and_focus(WidPlaylist)
        else :
            self._hideAll(event)
            self._show_and_focus(WidChannelRack)
            
            

    def Navigator(self, event):
        if event.data2 in range(65,73) :
            event.data2 = 65
        elif event.data2 in range(55,63) :
            event.data2 = 62
        
        if self.snapToScaleUnderPressure:
            self.snapToScaleJustEdited = True
            if event.data2 == 62 :
                self.keyScaler.previousScale()
                self._navigation.SnapRefresh(self.keyScaler.getCurrentScaleName())
            elif event.data2 == 65 :
                self.keyScaler.nextScale()
                self._navigation.SnapRefresh(self.keyScaler.getCurrentScaleName())
            return True
            
        if ui.getFocused(WidPlugin) == True :
            self._hideAll(event)         
        elif ui.getFocused(WidBrowser) :
            if not ui.isInPopupMenu() :  
                if event.data2 == 62 :
                    ui.previous()
                elif event.data2 == 65 :
                    ui.next()
                self._navigation.HintRefresh(ui.getFocusedNodeCaption())
            else :
                if event.data2 == 62 :
                    ui.up()
                elif event.data2 == 65 :
                    ui.down()
                self._navigation.HintRefresh(ui.getFocusedNodeCaption())
        elif ui.getFocused(WidChannelRack) :
            self._show_and_focus(WidChannelRack)
            if event.data2 == 62 :
                self._show_and_focus(WidChannelRack)
                self._hideAll(event)
                ui.previous()
                mixer.setTrackNumber(channels.getTargetFxTrack(channels.selectedChannel()),3)
            elif event.data2 == 65 :  
                self._show_and_focus(WidChannelRack)
                self._hideAll(event)
                ui.next()
                mixer.setTrackNumber(channels.getTargetFxTrack(channels.selectedChannel()),3)
        else :
            ui.setFocused(WidChannelRack)
        
        return True

    def PluginTest(self, event) :
        if ui.getFocused(WidPlugin) :
            if channels.selectedChannel(1) != -1 :
                string = plugins.getPluginName(channels.selectedChannel())
                if string in ArturiaVCOL.V_COL :
                    self.ForwardAnalogLab(event)
                else :
                    self.PluginPreset(event)
        else :
            if event.data2 > 64 :
                self.FastForward(event)
            else :
                self.Rewind(event)
        return True

    def showPlugin(self, event) :
        if channels.selectedChannel(1) != -1 :
            channels.showEditor(channels.selectedChannel())


    # FUNCTIONS
    def Redo(self, event):
        isPressed = self._is_pressed(event)
        if isPressed:
            general.undoDown()
            self._navigation.RedoRefresh()

        self._mk3.LightReturn().updateUndoRedo(isPressed)
        return True

    def Undo(self, event):
        isPressed = self._is_pressed(event)
        if isPressed:
            general.undoUp()
            self._navigation.UndoRefresh()

        self._mk3.LightReturn().updateUndoRedo(isPressed)
        return True
        

    def Record(self, event) :
        transport.record()
        #self._navigation.RecordRefresh()
        return True
    
    
    def Start(self, event) :
        transport.start()
        #self._navigation.PlayRefresh()
        return True
    
    
    def SnapToScale(self, event):
        isPressed = self._is_pressed(event)

        # If pressed...
        if isPressed:
            self.snapToScaleUnderPressure = True

            # ...And not active, activate it
            if not self.snapToScale:
                self.snapToScaleJustEdited = True
                self.snapToScale = True
                    
                self._navigation.SnapRefresh(self.keyScaler.getCurrentScaleName())

        # If release and active, deactivate it
        else:
            self.snapToScaleUnderPressure = False

            if self.snapToScale and not self.snapToScaleJustEdited:
                self.snapToScale = False
                self._navigation.SnapRefresh("OFF")
            
            self.snapToScaleJustEdited = False


        self._mk3.LightReturn().updateSnapToScale(self.shift, self.snapToScale)
        return True

    def Stop(self, event):
        isPressed = self._is_pressed(event)
        if isPressed:
            transport.stop()
            send_to_device(bytes([0x02, 0x02, 0x16, 0x08, 0x7F, 0x7F, 0x7F]))
            # self._navigation.StopRefresh()
        
        self._mk3.LightReturn().updateStop(isPressed)
        return True

    def Loop(self, event) :
        transport.globalTransport(midi.FPT_LoopRecord, 1)
        self._navigation.LoopRefresh()
        return True

    def StepByStep(self, event):
        transport.globalTransport(midi.FPT_StepEdit, 1)
        self._navigation.StepByStepRefresh()
        return True

    def WaitForInput(self, event):
        transport.globalTransport(midi.FPT_WaitForInput, 1)
        self._navigation.WaitForInputRefresh()
        return True

    def Overdub(self, event) :
        transport.globalTransport(midi.FPT_Overdub,1)
        self._navigation.OverdubRefresh()
        
   
    def FastForward(self, event) :
        pos = transport.getSongPos(2)
        transport.setSongPos(pos+24,2)
        self._navigation.FastForwardRefresh()
        return True

    
    def Rewind(self, event) :
        pos = transport.getSongPos(2)
        transport.setSongPos(pos-24,2)
        self._navigation.RewindRefresh()
        return True


    def SetClick(self, event) :
        transport.globalTransport(midi.FPT_Metronome,1)
        self._navigation.MetronomeRefresh()
        return True
        
    def Tap(self, event) :
        if self._is_pressed(event): # on press
            pass
        else:
            # on release
            general.undoUp()
            # self._navigation.Undo()
        
        # if self._is_pressed(event) :
        #     transport.globalTransport(midi.FPT_TapTempo,1)
        #     send_to_device(bytes([0x02, 0x02, 0x16, 0x5B, 0x7F, 0x7F, 0x7F]))
        #     send_to_device(bytes([0x02, 0x01, 0x16, 0x5B, 0x7F, 0x7F, 0x7F]))
        #     self._navigation.TapTempoRefresh()
        # else :
        #     send_to_device(bytes([0x02, 0x02, 0x16, 0x5B, 0x14, 0x14, 0x14]))
        #     send_to_device(bytes([0x02, 0x01, 0x16, 0x5B, 0x14, 0x14, 0x14]))

    def SetVolumeTrack(self, event) :
        if not ui.getFocused(WidPlugin) : 
            value = event.data2/127
            mixer.setTrackVolume(mixer.trackNumber(),value, 2)
            self._navigation.VolumeChRefresh(value, 4)
        else :
            self.Plugin(event)
        return True
            
   
    def SetPanTrack(self, event) :
        if not ui.getFocused(WidPlugin) :
            value = round(event.data2*(128/127)-64)/64
            mixer.setTrackPan(mixer.trackNumber(),value, 2)
            self._navigation.PanChRefresh(value, 3)
        else :
            self.Plugin(event)
        return True
            

    def AnalogLabPreset(self, event) :
        if event.data2 == 65 :
            device.forwardMIDICC(event.status + (0x1D << 8) + (0x7F << 16) + (PORT_MIDICC_ANALOGLAB << 24))
        elif event.data2 == 63 :
            device.forwardMIDICC(event.status + (0x1C << 8) + (0x7F << 16) + (PORT_MIDICC_ANALOGLAB << 24))


    def Plugin(self, event) :

        global UPDATE_KNOB
        global KNOB_HW_VALUE
        
        if event.data1 != 29 :
            if ui.getFocused(WidPlugin) :
                global DISPLAY_TYPE
                if event.status != 224 :
                    clef = event.data1
                else :
                    clef = 224
                    
                parameter, value, mapped = MiniLab3Plugin.Plugin(event, clef)

                if event.data1 in KNOB_ID :
                    self._navigation.PluginRefresh(parameter, value, mapped, event.data2, 3)
                    DISPLAY_TYPE = 3
                elif event.data1 != 1 :
                    self._navigation.PluginRefresh(parameter, value, mapped, event.data2, 4)
                    DISPLAY_TYPE = 4
            else :
                self._navigation.NoPlugin()
        else :
            clef = event.data1
            KNOB_HW_VALUE, mapped = MiniLab3Plugin.Plugin(event, 0)
        
            UPDATE_KNOB = mapped
        
        return True

    def PluginPreset(self, event) :
        if event.data2 in range(65,73) :
            if channels.selectedChannel(1) != -1 :
                plugins.nextPreset(channels.selectedChannel())
        elif event.data2 in range(55,63) :
            if channels.selectedChannel(1) != -1 :
                plugins.prevPreset(channels.selectedChannel())
        
        #self.SetParamValue(event)
    
    
    def ForwardAnalogLab(self, event) :
        #print(plugins.getPluginName(channels.selectedChannel()))
        if channels.selectedChannel(1) != -1 :
            if plugins.isValid(channels.selectedChannel(1)) : 
                if plugins.getPluginName(channels.selectedChannel()) in ArturiaVCOL.V_COL :
                    device.forwardMIDICC(event.status + (event.data1 << 8) + (event.data2 << 16) + (PORT_MIDICC_ANALOGLAB << 24))
                else :
                    self.Plugin(event)
        return True
        
    # UTILITY
    def FakeMIDImsg(self) :
        transport.globalTransport(midi.FPT_Punch,1)


    def ShiftIsPressed(self, event) :
        if ui.getFocused(WidBrowser) :
            if ui.isInPopupMenu():
                transport.globalTransport(midi.FPT_Escape, 1)
                self._navigation.BackRefresh()
        return self._is_pressed(event)


    def ShiftOn(self, event) :
        self.shift = self.ShiftIsPressed(event)
        self._mk3.LightReturn().updateAll(self.shift, self.snapToScale)
        return True

    def PadOn(self, index) :
        index= index-36
        PAD_MATRIX_STATE[index] = 1
        # print(PAD_MATRIX_STATE)
        self.PadRefresh(PAD_MATRIX_STATE)
 
    
    def PadOff(self, index) :
        index = index-36
        PAD_MATRIX_STATE[index] = 0
        # print(PAD_MATRIX_STATE)
        self.PadRefresh(PAD_MATRIX_STATE)


    def PadRefresh(self, Matrix) :
        print("PAD REFRESHING")
        for i in range(16) :
            if PAD_MATRIX_STATE[i] :
                send_to_device(bytes([0x02, 0x02, 0x16, PAD_MATRIX[i], 0x58, 0x58, 0x58, 0x7F]))
            else :
                send_to_device(bytes([0x02, 0x02, 0x16, PAD_MATRIX[i], 0x14, 0x14, 0x14, 0x7F]))
                

        
    def SetParamValue(self, event) :
        
        self.Plugin(event)
        
        if UPDATE_KNOB :
            print("UPDATE KNOB ?")
            for i in range (8) :
                value = round(KNOB_HW_VALUE[i]*127)
                #print(value)
                send_to_device(bytes([0x21, 0x10, 0x40, KNOB_HW_ID[i], 0x00, value]))

    def DAWMemory(self) :
        global MEMORY
        #print("MEMORY = ",MEMORY)
        MEMORY = 2
        return True
        
    def ArturiaMemory(self) :
        global MEMORY
        #print("MEMORY = ",MEMORY)
        MEMORY = 1
        return True
