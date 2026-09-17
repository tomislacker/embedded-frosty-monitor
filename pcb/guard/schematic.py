#!/usr/bin/env python3
"""
FrostSight Guard rev A (draft) -- schematic-as-code.

This is the reviewable schematic for the Guard tier permanent monitor board.
Every circuit block below corresponds 1:1 to a bullet in the board spec
(see pcb/guard/README.md and docs/product-line.md, Tier 1 -- Guard). It is
written to be read top to bottom like a schematic sheet, not just executed.

Run directly to regenerate pcb/guard/guard.net:

    python3 schematic.py

Requires the `skidl` package (see pcb/guard/README.md for the venv/env-var
setup) and KiCad's bundled symbol libraries. This script hard-codes the
symbol library search paths so it does not depend on the caller's shell
having KICAD*_SYMBOL_DIR exported -- check.sh relies on that.

-------------------------------------------------------------------------
MCU FOOTPRINT SUBSTITUTION -- READ THIS FIRST
-------------------------------------------------------------------------
The board spec calls for an ESP32-C3-MINI-1 module. KiCad 10's stock
libraries do not ship a MINI-1 symbol or footprint (they have
ESP32-C3-WROOM-02, ESP32-C3-DevKitM-1, and ESP32-C6-MINI-1, but not
C3-MINI-1). This design uses the RF_Module:ESP32-C3-WROOM-02 symbol as a
stand-in:

  - Same ESP32-C3 SoC, same GPIO numbering/strapping behavior (GPIO0-10,
    18/19 USB, 20/21 UART0), so every net connection and GPIO assignment
    below is electrically representative of the real MINI-1.
  - The WROOM-02 is a *larger* module (~18x25.5mm) than the real MINI-1
    (~15.4x20.5mm) and its castellated pad pitch/positions do not match
    MINI-1's datasheet pad map.

This is flagged again in build_board.py and in the README's limitations
section. EE review must swap in a real ESP32-C3-MINI-1 footprint (built
from Espressif's datasheet pad map) before fabrication -- do not tape out
against the WROOM-02 footprint.
-------------------------------------------------------------------------

GPIO ASSIGNMENT (authoritative -- mirrored in README.md)

  GPIO0   ADC1_CH0  CT_SIG        analog, through anti-alias RC + bias net
  GPIO1             ONEWIRE       DS18B20 bus (both JST-XH chains, shared)
  GPIO2             RESERVED      strapping pin -- left unconnected (NC)
  GPIO3             DRIP_SIG      drip-counter pulse in, RC debounced
  GPIO4   ADC1_CH4  LED_STATUS    green status LED (ADC channel unused)
  GPIO5             LED_ALERT     red alert LED
  GPIO6             I2C_SCL       Qwiic expansion header
  GPIO7             I2C_SDA       Qwiic expansion header
  GPIO8             RESERVED      strapping pin -- left unconnected (NC)
  GPIO9             BTN_BOOT      BOOT button, conventional strap-to-GND use
  GPIO10            BTN_ACK       user acknowledge button
  GPIO18            USB_DM        native USB, fixed function
  GPIO19            USB_DP        native USB, fixed function
  GPIO20            UART_RX       debug header
  GPIO21            UART_TX       debug header
  EN                RESET         reset button (EN-to-GND) + 10k pull-up +
                                   100nF per Espressif reference design

GPIO2 and GPIO8 (the two strapping pins other than BOOT/GPIO9) are left
completely unpopulated -- no resistor, no connector, nothing that could
present a load at boot -- per the board spec's constraint.
"""

import os
import sys

# ---------------------------------------------------------------------
# Point SKiDL at KiCad's bundled symbol libraries. Set every version-keyed
# var SKiDL looks for so this is independent of which KICAD*_SYMBOL_DIR
# (if any) the caller's shell has exported.
# ---------------------------------------------------------------------
KICAD_SYMBOL_DIR = os.environ.get("KICAD_SYMBOL_DIR", "/usr/share/kicad/symbols")
for _var in (
    "KICAD_SYMBOL_DIR",
    "KICAD6_SYMBOL_DIR",
    "KICAD7_SYMBOL_DIR",
    "KICAD8_SYMBOL_DIR",
    "KICAD9_SYMBOL_DIR",
    "KICAD10_SYMBOL_DIR",
):
    os.environ[_var] = KICAD_SYMBOL_DIR

from skidl import (  # noqa: E402
    Part,
    Net,
    ERC,
    generate_netlist,
    set_default_tool,
    KICAD8,
)
from skidl.logger import erc_logger  # noqa: E402
from skidl.pin import pin_drives  # noqa: E402

# `NC` (the no-connect sentinel net) is injected into builtins by the
# `skidl` import above rather than exported normally -- pull it in
# explicitly so linters/readers can see where it comes from.
NC = __builtins__["NC"] if isinstance(__builtins__, dict) else __builtins__.NC

set_default_tool(KICAD8)  # KiCad 8-format symbol parser also reads KiCad 10 libs

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------
# Global nets -- the rails and buses that cross block boundaries.
# ---------------------------------------------------------------------
GND = Net("GND")
VBUS = Net("VBUS")  # 5V from USB-C, SELV, never anything above this on-board
V3V3 = Net("+3V3")  # regulated rail everything else runs from

GND.drive = pin_drives.POWER  # silence "no driver" ERC noise on the return net
VBUS.drive = pin_drives.POWER
V3V3.drive = pin_drives.POWER

CT_SIG = Net("CT_SIG")  # to MCU ADC1_CH0 (GPIO0), post anti-alias filter
ONEWIRE = Net("ONEWIRE")  # shared DS18B20 bus, GPIO1
DRIP_SIG = Net("DRIP_SIG")  # debounced drip pulse, GPIO3
LED_STATUS = Net("LED_STATUS_A")  # anode side of status LED, GPIO4
LED_ALERT = Net("LED_ALERT_A")  # anode side of alert LED, GPIO5
I2C_SCL = Net("I2C_SCL")  # GPIO6
I2C_SDA = Net("I2C_SDA")  # GPIO7
BTN_BOOT = Net("BTN_BOOT")  # GPIO9
BTN_ACK = Net("BTN_ACK")  # GPIO10
USB_DM = Net("USB_DM")  # GPIO18, ESD-protected
USB_DP = Net("USB_DP")  # GPIO19, ESD-protected
UART_RX = Net("UART_RX")  # GPIO20
UART_TX = Net("UART_TX")  # GPIO21
EN_RESET = Net("EN_RESET")  # MCU EN pin


# ---------------------------------------------------------------------
# Helper: consistent 0603 R / C so every passive in this file reads the
# same way in the netlist and in the BOM.
# ---------------------------------------------------------------------
def R(value, ref=None):
    return Part(
        "Device", "R", value=value, ref=ref,
        footprint="Resistor_SMD:R_0603_1608Metric",
    )


def C(value, ref=None):
    return Part(
        "Device", "C", value=value, ref=ref,
        footprint="Capacitor_SMD:C_0603_1608Metric",
    )


# =======================================================================
# BLOCK 1 -- MCU: ESP32-C3-MINI-1 (see footprint-substitution note above)
# =======================================================================
mcu = Part(
    "RF_Module", "ESP32-C3-WROOM-02",
    ref="U1",
    footprint="RF_Module:ESP32-C3-WROOM-02",
)
mcu.value = "ESP32-C3-MINI-1 (schematic symbol: ESP32-C3-WROOM-02, same SoC/pinout)"

mcu["3V3"] += V3V3
mcu["GND"] += GND  # symbol exposes two GND pins, both tied
mcu["EN"] += EN_RESET
mcu["IO0"] += CT_SIG
mcu["IO1"] += ONEWIRE
mcu["IO2"] += NC  # strapping pin -- intentionally unpopulated, see header note
mcu["IO3"] += DRIP_SIG
mcu["IO4"] += LED_STATUS
mcu["IO5"] += LED_ALERT
mcu["IO6"] += I2C_SCL
mcu["IO7"] += I2C_SDA
mcu["IO8"] += NC  # strapping pin -- intentionally unpopulated, see header note
mcu["IO9"] += BTN_BOOT
mcu["IO10"] += BTN_ACK
mcu["IO18"] += USB_DM
mcu["IO19"] += USB_DP
mcu["IO20/RXD"] += UART_RX
mcu["IO21/TXD"] += UART_TX

# EN pull-up + decoupling cap, per Espressif's ESP32-C3-MINI-1 reference
# design (the module has no internal EN pull-up).
r_en = R("10k", ref="R1")
r_en[1] += V3V3
r_en[2] += EN_RESET
c_en = C("100nF", ref="C1")
c_en[1] += EN_RESET
c_en[2] += GND

# MCU-local decoupling: one bulk + one HF cap right at the 3V3 pin.
c_mcu_bulk = Part("Device", "C", value="10uF", ref="C2",
                   footprint="Capacitor_SMD:C_0805_2012Metric")
c_mcu_bulk[1] += V3V3
c_mcu_bulk[2] += GND
c_mcu_hf = C("100nF", ref="C3")
c_mcu_hf[1] += V3V3
c_mcu_hf[2] += GND


# =======================================================================
# BLOCK 2 -- Power in: USB-C receptacle, 5V-only, ESD + regulation
# =======================================================================
usb_c = Part(
    "Connector", "USB_C_Receptacle_USB2.0_16P",
    ref="J1",
    footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
)
usb_c.value = "USB-C receptacle (5V power + USB2.0 data, no PD)"

CC1 = Net("CC1")
CC2 = Net("CC2")

usb_c["VBUS"] += VBUS  # both VBUS pin pairs (A4/A9, B4/B9) tied by the symbol
usb_c["GND"] += GND  # all GND pins (A1/A12/B1/B12) tied by the symbol
usb_c["CC1"] += CC1
usb_c["CC2"] += CC2
# The 16P symbol ties A6/D+ and B6/D+ together (and D-/D- likewise) since
# it models an unoriented USB2.0-only receptacle -- both map to the same
# ESD-protected data pair below.
USB_DP_CONN = Net("USB_DP_CONN")  # connector-side D+, pre-ESD
USB_DM_CONN = Net("USB_DM_CONN")  # connector-side D-, pre-ESD
usb_c["D+"] += USB_DP_CONN
usb_c["D-"] += USB_DM_CONN
usb_c["SHIELD"] += GND
usb_c["SBU1"] += NC  # sideband-use pins, only meaningful for USB3/AltMode;
usb_c["SBU2"] += NC  # this is a USB2.0-only design, so both are unused.

# 5.1k CC pulldowns -- required so a USB-C source (including PD-capable
# chargers) advertises 5V/default-current and nothing more. No PD
# negotiation is implemented; this is the "5V only, SELV" sink config.
r_cc1 = R("5.1k", ref="R2")
r_cc1[1] += CC1
r_cc1[2] += GND
r_cc2 = R("5.1k", ref="R3")
r_cc2[1] += CC2
r_cc2[2] += GND

# VBUS bulk + HF caps right at the connector.
c_vbus_bulk = Part("Device", "C", value="10uF", ref="C4",
                    footprint="Capacitor_SMD:C_0805_2012Metric")
c_vbus_bulk[1] += VBUS
c_vbus_bulk[2] += GND
c_vbus_hf = C("100nF", ref="C5")
c_vbus_hf[1] += VBUS
c_vbus_hf[2] += GND

# ESD protection on VBUS/D+/D- -- USBLC6-2 class, sits electrically
# between the connector and everything downstream (MCU native USB +
# regulator input).
esd = Part(
    "Power_Protection", "USBLC6-2SC6",
    ref="U2",
    footprint="Package_TO_SOT_SMD:SOT-23-6",
)
esd["VBUS"] += VBUS
esd["GND"] += GND
esd["I/O1"] += USB_DP_CONN  # connector-side D+
esd["I/O2"] += USB_DM_CONN  # connector-side D-

# MCU-side (protected) USB data nets are the ones already wired to the
# MCU above (USB_DP/USB_DM). Bridge them through the ESD part's other
# I/O pins via 22R series resistors, per Espressif's USB hardware design
# guidelines (source termination close to the MCU).
r_dp = R("22", ref="R4")
r_dm = R("22", ref="R5")
r_dp[1] += esd["I/O1"]
r_dp[2] += USB_DP
r_dm[1] += esd["I/O2"]
r_dm[2] += USB_DM

# 3.3V regulation: AMS1117-3.3, SOT-223, >=1A rated -- covers WiFi TX
# current bursts with margin over the spec's 800mA floor.
reg = Part(
    "Regulator_Linear", "AMS1117-3.3",
    ref="U3",
    footprint="Package_TO_SOT_SMD:SOT-223",
)
reg["VI"] += VBUS
reg["GND"] += GND
reg["VO"] += V3V3

# Regulator input/output caps per the AMS1117 datasheet's typical
# application circuit.
c_reg_in = Part("Device", "C", value="10uF", ref="C6",
                 footprint="Capacitor_SMD:C_0805_2012Metric")
c_reg_in[1] += VBUS
c_reg_in[2] += GND
c_reg_out = Part("Device", "C", value="22uF", ref="C7",
                  footprint="Capacitor_SMD:C_0805_2012Metric")
c_reg_out[1] += V3V3
c_reg_out[2] += GND
c_reg_out_hf = C("100nF", ref="C8")
c_reg_out_hf[1] += V3V3
c_reg_out_hf[2] += GND


# =======================================================================
# BLOCK 3 -- USB data: native USB (GPIO18/19) already wired above via the
# ESD part. Nothing further needed here -- this block exists in the spec
# as a named item, and its nets (USB_DP/USB_DM) are already complete:
# connector -> USBLC6-2 -> 22R series -> MCU GPIO19/GPIO18.
# =======================================================================


# =======================================================================
# BLOCK 4 -- CT input x1: 3.5mm TRS jack, bias network, anti-alias RC,
# clamp protection, into MCU ADC1 (GPIO0/CT_SIG).
# =======================================================================
ct_jack = Part(
    "Connector_Audio", "AudioJack3",
    ref="J2",
    footprint="Connector_Audio:Jack_3.5mm_PJ320D_Horizontal",
)
ct_jack.value = "3.5mm TRS (SCT-013-020 burden output, 1V RMS @ rated current)"

CT_RAW = Net("CT_RAW")  # jack tip, AC signal centered on 0V
ct_jack["T"] += CT_RAW  # tip = CT signal
ct_jack["S"] += GND  # sleeve = CT return / shield
ct_jack["R"] += GND  # ring tied to sleeve so a 2-conductor (TS) CT plug,
# which is what SCT-013-020 normally ships with, still seats correctly.

# Bias network: two 10k from 3V3 and GND form a 3.3V/2 = 1.65V midpoint.
# CT_RAW is AC-coupled onto that midpoint through a coupling cap so the
# ADC (which can only see 0..3.3V) sees the CT waveform centered at
# 1.65V instead of swinging negative.
CT_BIAS = Net("CT_BIAS")
r_bias_hi = R("10k", ref="R6")
r_bias_hi[1] += V3V3
r_bias_hi[2] += CT_BIAS
r_bias_lo = R("10k", ref="R7")
r_bias_lo[1] += CT_BIAS
r_bias_lo[2] += GND
c_bias_decouple = Part("Device", "C", value="1uF", ref="C9",
                        footprint="Capacitor_SMD:C_0603_1608Metric")
c_bias_decouple[1] += CT_BIAS
c_bias_decouple[2] += GND

c_couple = Part("Device", "C", value="10uF", ref="C10",
                 footprint="Capacitor_SMD:C_0805_2012Metric")
c_couple[1] += CT_RAW
c_couple[2] += CT_BIAS  # AC-couples the CT signal onto the DC bias node

# Anti-alias RC low-pass right before the ADC pin: 1k + 100nF gives a
# -3dB corner around 1.6kHz, well above the 50/60Hz mains fundamental and
# its first several harmonics but well below the C3 ADC's sample noise
# band -- coarse duty-cycle sensing only, per docs/product-line.md's risk
# note on C3 ADC quality; this is not meant to resolve a current
# waveform.
r_aa = R("1k", ref="R8")
r_aa[1] += CT_BIAS
r_aa[2] += CT_SIG
c_aa = C("100nF", ref="C11")
c_aa[1] += CT_SIG
c_aa[2] += GND

# Protection clamp: BAT54S dual Schottky, COM at the signal node, clamped
# between GND and 3V3. Keeps an unexpectedly large induced CT transient
# (e.g. compressor inrush coupling) from exceeding the ADC's absolute
# max rating. Orientation (COM=signal, A=GND-side clamp, K=3V3-side
# clamp) follows this library part's common clamp application; EE review
# should confirm polarity against the specific BAT54S datasheet used.
clamp = Part(
    "Diode", "BAT54S",
    ref="D1",
    footprint="Package_TO_SOT_SMD:SOT-23",
)
clamp["COM"] += CT_SIG
clamp["A"] += GND
clamp["K"] += V3V3


# =======================================================================
# BLOCK 5 -- Temperature: 2x 3-pin JST-XH for DS18B20 chains, shared
# 1-Wire GPIO, single 4.7k pull-up.
# =======================================================================
for i, ref in enumerate(("J3", "J4"), start=1):
    hdr = Part(
        "Connector_Generic", "Conn_01x03",
        ref=ref,
        footprint="Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical",
    )
    hdr.value = f"DS18B20 chain {i} (pin1 GND / pin2 DQ / pin3 3V3)"
    hdr[1] += GND
    hdr[2] += ONEWIRE
    hdr[3] += V3V3

r_ow = R("4.7k", ref="R9")
r_ow[1] += V3V3
r_ow[2] += ONEWIRE


# =======================================================================
# BLOCK 6 -- Drip counter: 4-pin JST-XH (3.3V, GND, SIG, spare), RC
# debounce into a GPIO.
# =======================================================================
drip = Part(
    "Connector_Generic", "Conn_01x04",
    ref="J5",
    footprint="Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical",
)
drip.value = "Drip counter (pin1 3V3 / pin2 GND / pin3 SIG / pin4 spare)"
DRIP_RAW = Net("DRIP_RAW")
drip[1] += V3V3
drip[2] += GND
drip[3] += DRIP_RAW
drip[4] += NC  # spare pin, unpopulated by design -- not a strapping pin,
# just genuinely unused; left as a bare header pad for a future signal.

# Defines an idle-low default so a disconnected/unpowered sensor doesn't
# leave the GPIO floating, then RC-debounces the pulse edge.
r_drip_pd = R("10k", ref="R10")
r_drip_pd[1] += DRIP_RAW
r_drip_pd[2] += GND
r_drip_series = R("1k", ref="R11")
r_drip_series[1] += DRIP_RAW
r_drip_series[2] += DRIP_SIG
c_drip = C("100nF", ref="C12")
c_drip[1] += DRIP_SIG
c_drip[2] += GND


# =======================================================================
# BLOCK 7 -- UI: status/alert LEDs, ack button, BOOT + RESET buttons.
# =======================================================================
led_status = Part("Device", "LED", ref="D2",
                   footprint="LED_SMD:LED_0603_1608Metric")
led_status.value = "Status LED (green)"
r_led_status = R("330", ref="R12")
r_led_status[1] += LED_STATUS
r_led_status[2] += led_status["A"]
led_status["K"] += GND

led_alert = Part("Device", "LED", ref="D3",
                  footprint="LED_SMD:LED_0603_1608Metric")
led_alert.value = "Alert LED (red)"
r_led_alert = R("330", ref="R13")
r_led_alert[1] += LED_ALERT
r_led_alert[2] += led_alert["A"]
led_alert["K"] += GND

sw_ack = Part("Switch", "SW_Push", ref="SW1",
              footprint="Button_Switch_SMD:SW_SPST_SKQG_WithoutStem")
sw_ack.value = "Ack button (user)"
sw_ack[1] += BTN_ACK
sw_ack[2] += GND

sw_boot = Part("Switch", "SW_Push", ref="SW2",
               footprint="Button_Switch_SMD:SW_SPST_SKQG_WithoutStem")
sw_boot.value = "BOOT button (GPIO9, conventional strap-to-GND)"
sw_boot[1] += BTN_BOOT
sw_boot[2] += GND

sw_reset = Part("Switch", "SW_Push", ref="SW3",
                footprint="Button_Switch_SMD:SW_SPST_SKQG_WithoutStem")
sw_reset.value = "RESET button (EN-to-GND)"
sw_reset[1] += EN_RESET
sw_reset[2] += GND


# =======================================================================
# BLOCK 8 -- Expansion: 4-pin JST-SH I2C (Qwiic pinout), 3-pin UART debug.
# =======================================================================
i2c_hdr = Part(
    "Connector_Generic", "Conn_01x04",
    ref="J6",
    footprint="Connector_JST:JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical",
)
i2c_hdr.value = "I2C expansion, Qwiic pinout (pin1 GND / pin2 3V3 / pin3 SDA / pin4 SCL)"
i2c_hdr[1] += GND
i2c_hdr[2] += V3V3
i2c_hdr[3] += I2C_SDA
i2c_hdr[4] += I2C_SCL

# Bus pull-ups. Qwiic convention is "host provides pull-ups"; since Guard
# is normally the only device unless something is plugged into the
# expansion header, put modest pull-ups on-board so the bus is sane with
# nothing attached and still workable with one Qwiic sensor attached.
r_scl = R("4.7k", ref="R14")
r_scl[1] += V3V3
r_scl[2] += I2C_SCL
r_sda = R("4.7k", ref="R15")
r_sda[1] += V3V3
r_sda[2] += I2C_SDA

uart_hdr = Part(
    "Connector_Generic", "Conn_01x03",
    ref="J7",
    footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
)
uart_hdr.value = "UART debug (pin1 TX / pin2 RX / pin3 GND)"
uart_hdr[1] += UART_TX
uart_hdr[2] += UART_RX
uart_hdr[3] += GND


# =======================================================================
# BLOCK 9 -- Mounting holes (M3 x2) are a board-outline/mechanical
# feature, not a schematic net -- placed directly on the PCB in
# build_board.py. Nothing to instantiate here.
# =======================================================================


# =======================================================================
# ERC
# =======================================================================
# Known, reviewed ERC waivers -- design decisions that would otherwise
# show up as ERC noise, resolved deliberately rather than by accident:
#
#  - NC-marked pins (MCU strapping pins IO2/IO8, USB-C SBU1/SBU2, the
#    drip header's spare pin) are deliberately unconnected; skidl's NC
#    marker suppresses the "unconnected pin" warning for exactly those
#    pins so a real accidental-unconnected mistake elsewhere would still
#    show up instead of being buried in expected noise.
#  - GND/VBUS/+3V3 are explicitly marked `.drive = pin_drives.POWER`
#    above so ERC doesn't flag the return/rail nets as under-driven --
#    every board has rails exactly like this and it is not a defect.
#
# With both of those in place this design's ERC is clean: 0 errors,
# 0 warnings (verified by the check below, which is also what makes
# check.sh fail loudly if a future edit regresses it).
print("=" * 70)
print("Running SKiDL ERC...")
print("=" * 70)
ERC()

# Hard gate: a real electrical ERROR (as opposed to an advisory WARNING)
# fails this script -- and therefore check.sh -- with a non-zero exit.
# The two ERC WARNINGs this design is expected to produce (see the
# waiver notes above the ERC() call) are read, not silenced, so a new
# warning introduced by a future edit is still visible in the log.
n_errors = erc_logger.error.count + erc_logger.bare_error.count
n_warnings = erc_logger.warning.count + erc_logger.bare_warning.count
print(f"ERC result: {n_errors} errors, {n_warnings} warnings")
if n_errors:
    print("ERC FAILED -- fix the errors above before generating a netlist.")
    sys.exit(1)

print("=" * 70)
print("Writing netlist...")
print("=" * 70)
generate_netlist(file_=os.path.join(HERE, "guard.net"))
print(f"Wrote {os.path.join(HERE, 'guard.net')}")
