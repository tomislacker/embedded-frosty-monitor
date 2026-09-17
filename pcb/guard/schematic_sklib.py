from collections import defaultdict
from skidl import Pin, Part, Alias, SchLib, SKIDL, TEMPLATE

from skidl.pin import pin_types

SKIDL_lib_version = '0.0.1'

schematic = SchLib(tool=SKIDL).add_parts(*[
        Part(**{ 'name':'ESP32-C3-WROOM-02', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'ESP32-C3-WROOM-02'}), 'ref_prefix':'U', 'fplist':['RF_Module:ESP32-C3-WROOM-02'], 'footprint':'RF_Module:ESP32-C3-WROOM-02', 'keywords':'esp32 espressif WiFi Bluetooth LE', 'description':'802.11 b/g/n WiÂ\xadFi and Bluetooth 5 module, ESP32Â\xadC3 SoC, RISCÂ\xadV microprocessor, On-board antenna', 'datasheet':'https://www.espressif.com/sites/default/files/documentation/esp32-c3-wroom-02_datasheet_en.pdf', 'pins':[
            Pin(num='1',name='3V3',func=pin_types.PWRIN,unit=1),
            Pin(num='2',name='EN',func=pin_types.INPUT,unit=1),
            Pin(num='3',name='IO4',func=pin_types.BIDIR,unit=1),
            Pin(num='4',name='IO5',func=pin_types.BIDIR,unit=1),
            Pin(num='5',name='IO6',func=pin_types.BIDIR,unit=1),
            Pin(num='6',name='IO7',func=pin_types.BIDIR,unit=1),
            Pin(num='7',name='IO8',func=pin_types.BIDIR,unit=1),
            Pin(num='8',name='IO9',func=pin_types.BIDIR,unit=1),
            Pin(num='9',name='GND',func=pin_types.PWRIN,unit=1),
            Pin(num='10',name='IO10',func=pin_types.BIDIR,unit=1),
            Pin(num='11',name='IO20/RXD',func=pin_types.BIDIR,unit=1),
            Pin(num='12',name='IO21/TXD',func=pin_types.BIDIR,unit=1),
            Pin(num='13',name='IO18',func=pin_types.BIDIR,unit=1),
            Pin(num='14',name='IO19',func=pin_types.BIDIR,unit=1),
            Pin(num='15',name='IO3',func=pin_types.BIDIR,unit=1),
            Pin(num='16',name='IO2',func=pin_types.BIDIR,unit=1),
            Pin(num='17',name='IO1',func=pin_types.BIDIR,unit=1),
            Pin(num='18',name='IO0',func=pin_types.BIDIR,unit=1),
            Pin(num='19',name='GND',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'R', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'R'}), 'ref_prefix':'R', 'fplist':[''], 'footprint':'Resistor_SMD:R_0603_1608Metric', 'keywords':'R res resistor', 'description':'Resistor', 'datasheet':'', 'pins':[
            Pin(num='1',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'C', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'C'}), 'ref_prefix':'C', 'fplist':[''], 'footprint':'Capacitor_SMD:C_0603_1608Metric', 'keywords':'cap capacitor', 'description':'Unpolarized capacitor', 'datasheet':'', 'pins':[
            Pin(num='1',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'USB_C_Receptacle_USB2.0_16P', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'USB_C_Receptacle_USB2.0_16P'}), 'ref_prefix':'J', 'fplist':[''], 'footprint':'Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12', 'keywords':'usb universal serial bus type-C USB2.0', 'description':'USB 2.0-only 16P Type-C Receptacle connector', 'datasheet':'https://www.usb.org/sites/default/files/documents/usb_type-c.zip', 'pins':[
            Pin(num='A1',name='GND',func=pin_types.PASSIVE,unit=1),
            Pin(num='A4',name='VBUS',func=pin_types.PASSIVE,unit=1),
            Pin(num='A5',name='CC1',func=pin_types.BIDIR,unit=1),
            Pin(num='A6',name='D+',func=pin_types.BIDIR,unit=1),
            Pin(num='A7',name='D-',func=pin_types.BIDIR,unit=1),
            Pin(num='A8',name='SBU1',func=pin_types.BIDIR,unit=1),
            Pin(num='A9',name='VBUS',func=pin_types.PASSIVE,unit=1),
            Pin(num='A12',name='GND',func=pin_types.PASSIVE,unit=1),
            Pin(num='B1',name='GND',func=pin_types.PASSIVE,unit=1),
            Pin(num='B4',name='VBUS',func=pin_types.PASSIVE,unit=1),
            Pin(num='B5',name='CC2',func=pin_types.BIDIR,unit=1),
            Pin(num='B6',name='D+',func=pin_types.BIDIR,unit=1),
            Pin(num='B7',name='D-',func=pin_types.BIDIR,unit=1),
            Pin(num='B8',name='SBU2',func=pin_types.BIDIR,unit=1),
            Pin(num='B9',name='VBUS',func=pin_types.PASSIVE,unit=1),
            Pin(num='B12',name='GND',func=pin_types.PASSIVE,unit=1),
            Pin(num='SH',name='SHIELD',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'USBLC6-2SC6', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'USBLC6-2SC6'}), 'ref_prefix':'U', 'fplist':['Package_TO_SOT_SMD:SOT-666', 'Package_TO_SOT_SMD:SOT-23-6'], 'footprint':'Package_TO_SOT_SMD:SOT-23-6', 'keywords':'usb ethernet video', 'description':'Very low capacitance ESD protection diode, 2 data-line, SOT-23-6', 'datasheet':'https://www.st.com/resource/en/datasheet/usblc6-2.pdf', 'pins':[
            Pin(num='1',name='I/O1',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',name='GND',func=pin_types.PASSIVE,unit=1),
            Pin(num='3',name='I/O2',func=pin_types.PASSIVE,unit=1),
            Pin(num='4',name='I/O2',func=pin_types.PASSIVE,unit=1),
            Pin(num='5',name='VBUS',func=pin_types.PASSIVE,unit=1),
            Pin(num='6',name='I/O1',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'AMS1117-3.3', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'AMS1117-3.3'}), 'ref_prefix':'U', 'fplist':['Package_TO_SOT_SMD:SOT-223-3_TabPin2', 'Package_TO_SOT_SMD:SOT-223-3_TabPin2'], 'footprint':'Package_TO_SOT_SMD:SOT-223', 'keywords':'linear regulator ldo fixed positive', 'description':'1A Low Dropout regulator, positive, 3.3V fixed output, SOT-223', 'datasheet':'http://www.advanced-monolithic.com/pdf/ds1117.pdf', 'pins':[
            Pin(num='1',name='GND',func=pin_types.PWRIN,unit=1),
            Pin(num='2',name='VO',func=pin_types.PWROUT,unit=1),
            Pin(num='3',name='VI',func=pin_types.PWRIN,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'AudioJack3', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'AudioJack3'}), 'ref_prefix':'J', 'fplist':[''], 'footprint':'Connector_Audio:Jack_3.5mm_PJ320D_Horizontal', 'keywords':'audio jack receptacle stereo headphones phones TRS connector', 'description':'Audio Jack, 3 Poles (Stereo / TRS)', 'datasheet':'', 'pins':[
            Pin(num='R',func=pin_types.PASSIVE,unit=1),
            Pin(num='S',func=pin_types.PASSIVE,unit=1),
            Pin(num='T',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'BAT54S', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'BAT54S'}), 'ref_prefix':'D', 'fplist':['Package_TO_SOT_SMD:SOT-23'], 'footprint':'Package_TO_SOT_SMD:SOT-23', 'keywords':'schottky diode', 'description':'Vr 30V, If 200mA, Dual schottky barrier diode, in series, SOT-323', 'datasheet':'https://www.diodes.com/assets/Datasheets/ds11005.pdf', 'pins':[
            Pin(num='1',name='A',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',name='K',func=pin_types.PASSIVE,unit=1),
            Pin(num='3',name='COM',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'Conn_01x03', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'Conn_01x03'}), 'ref_prefix':'J', 'fplist':[''], 'footprint':'Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical', 'keywords':'connector', 'description':'Generic connector, single row, 01x03, script generated (kicad-library-utils/schlib/autogen/connector/)', 'datasheet':'', 'pins':[
            Pin(num='1',name='Pin_1',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',name='Pin_2',func=pin_types.PASSIVE,unit=1),
            Pin(num='3',name='Pin_3',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'Conn_01x04', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'Conn_01x04'}), 'ref_prefix':'J', 'fplist':[''], 'footprint':'Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical', 'keywords':'connector', 'description':'Generic connector, single row, 01x04, script generated (kicad-library-utils/schlib/autogen/connector/)', 'datasheet':'', 'pins':[
            Pin(num='1',name='Pin_1',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',name='Pin_2',func=pin_types.PASSIVE,unit=1),
            Pin(num='3',name='Pin_3',func=pin_types.PASSIVE,unit=1),
            Pin(num='4',name='Pin_4',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'LED', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'LED'}), 'ref_prefix':'D', 'fplist':[''], 'footprint':'LED_SMD:LED_0603_1608Metric', 'keywords':'LED diode', 'description':'Light emitting diode', 'datasheet':'', 'pins':[
            Pin(num='1',name='K',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',name='A',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'SW_Push', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'SW_Push'}), 'ref_prefix':'SW', 'fplist':[''], 'footprint':'Button_Switch_SMD:SW_SPST_SKQG_WithoutStem', 'keywords':'switch normally-open pushbutton push-button', 'description':'Push button switch, generic, two pins', 'datasheet':'', 'pins':[
            Pin(num='1',name='1',func=pin_types.PASSIVE),
            Pin(num='2',name='2',func=pin_types.PASSIVE)], 'unit_defs':[] })])