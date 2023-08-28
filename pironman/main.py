import os
import sys
import time
import threading
import RPi.GPIO as GPIO
from configparser import ConfigParser
from PIL import Image,ImageDraw,ImageFont
from oled import SSD1306_128_64, SSD1306_I2C_ADDRESS
from system_status import *
from utils import log, run_command
from app_info import __app_name__, __version__, username, user_home, config_file
from ws2812_RGB import WS2812, RGB_styles

# print info
line = '-'*24
_time = time.strftime("%y/%m/%d %H:%M:%S", time.localtime())
log('\n%s%s%s'%(line,_time,line), timestamp=False)
log('%s version: %s'%(__app_name__, __version__), timestamp=False)
log('username: %s'%username, timestamp=False)
log('config_file: %s'%config_file, timestamp=False)
# Kernel Version
status, result = run_command("uname -a")
if status == 0:
    log("\nKernel Version:", timestamp=False)
    log(f"{result}", timestamp=False)
# OS Version
status, result = run_command("lsb_release -a|grep Description")
if status == 0:
    log("OS Version:", timestamp=False)
    log(f"{result}", timestamp=False)
# PCB information
status, result = run_command("cat /proc/cpuinfo|grep -E \'Revision|Model\'")
if status == 0:
    log("PCB info:", timestamp=False)
    log(f"{result}", timestamp=False)

# region: config
power_key_pin = 16
fan_pin = 6
rgb_pin = 12
update_frequency = 0.5  # second
temp_higher_set = 70 # starting from this temperature the fan will spin at full speed
min_fan_pwm = 20 # minimum fan speed
max_fan_pwm = 100 # maximum fan speed, 100% by default

temp_unit = 'C' # 'C' or 'F'
fan_temp = 50 # celsius
fan_pwm = False # enables pwm fan mode
screen_always_on = False
screen_off_time = 60
rgb_switch = True
rgb_style = 'breath'  # 'breath', 'leap', 'flow', 'raise_up', 'colorful'
rgb_color = '#0a1aff'
rgb_blink_speed = 50
rgb_pwm_freq = 1000 # kHz

config = ConfigParser()
# check config_file
if not os.path.exists(config_file):
    log('Configuration file does not exist, recreating ...')
    # check $user_home/.config
    if not os.path.exists('%s/.config'%user_home):
        os.mkdir('%s/.config'%user_home)
        os.popen('sudo chmod 774 %s/.config'%user_home)
        run_command('sudo  chown %s %s/.config'%(username, user_home))
    # create config_file
    status, result = run_command(cmd='sudo mkdir -p  %s/.config/%s'%(user_home, __app_name__)
        +' && sudo touch %s'%config_file
        +' && sudo chmod -R 774 %s/.config/%s'%(user_home, __app_name__)
        +' && sudo chown -R %s %s/.config/%s'%(username, user_home, __app_name__)
    )
    if status != 0:
        log('create config_file failed:\n%s'%result)
        raise Exception(result)

# read config_file
try:
    config.read(config_file)
    temp_unit = config['all']['temp_unit']
    fan_temp = float(config['all']['fan_temp'])
    fan_pwm = config['all']['fan_pwm']
    if fan_pwm == 'True':
        fan_pwm = True
    else:
        fan_pwm = False
    screen_always_on = config['all']['screen_always_on']
    if screen_always_on == 'True':
        screen_always_on = True
    else:
        screen_always_on = False
    screen_off_time = int(config['all']['screen_off_time'])
    rgb_switch = (config['all']['rgb_switch'])
    if rgb_switch == 'False':
        rgb_switch = False
    else:
        rgb_switch = True
    rgb_style = str(config['all']['rgb_style'])
    rgb_color = str(config['all']['rgb_color'])
    rgb_blink_speed = int(config['all']['rgb_blink_speed'])
    rgb_pwm_freq = int(config['all']['rgb_pwm_freq'])
except:
    config['all'] ={
                    'fan_temp':fan_temp,
                    'fan_pwm':fan_pwm,
                    'screen_always_on':screen_always_on,
                    'screen_off_time':screen_off_time,
                    'rgb_switch':rgb_switch,
                    'rgb_style':rgb_style,
                    'rgb_color':rgb_color,
                    'rgb_blink_speed':rgb_blink_speed,
                    'rgb_pwm_freq':rgb_pwm_freq,
                    }
    with open(config_file, 'w') as f:
        config.write(f)

log("power_key_pin : %s"%power_key_pin)
log("fan_pin : %s"%fan_pin)
log("rgb_pin : %s"%rgb_pin)
log("update_frequency : %s"%update_frequency)
log("temp_unit : %s"%temp_unit)
log("fan_temp : %s"%fan_temp)
log("fan_pwm : %s"%fan_pwm)
log("screen_always_on : %s"%screen_always_on)
log("screen_off_time : %s"%screen_off_time)
log("rgb_switch: %s"%rgb_switch)
log("rgb_blink_speed : %s"%rgb_blink_speed)
log("rgb_pwm_freq : %s"%rgb_pwm_freq)
log("rgb_color : %s"%rgb_color)
log("\n")
# endregion: config

# region: oled init
oled_ok = False
oled_stat = False


try:
    run_command("sudo modprobe i2c-dev")
    oled = SSD1306_128_64()
    width = oled.width
    height = oled.height
    oled.begin()
    oled.clear()
    oled.on()

    image = Image.new('1', (width, height))
    draw = ImageDraw.Draw(image)
    font_8 = ImageFont.truetype('/opt/%s/Minecraftia-Regular.ttf'%__app_name__, 8)
    font_12 = ImageFont.truetype('/opt/%s/Minecraftia-Regular.ttf'%__app_name__, 12)

    def draw_text(text,x,y,fill=1):
        text = str(text)
        draw.text((x, y), text=text, font=font_8, fill=fill)

    oled_ok = True
    oled_stat = True
except Exception as e:
    log('oled init failed:\n%s'%e)
    oled_ok = False
    oled_stat = False

#endregion: oled init

# region: io control
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(fan_pin, GPIO.OUT)

fan_pwm_control = GPIO.PWM(fan_pin, 100)  # Frequency: 100 Hz
fan_pwm_control.start(0)  # Initialize with 0% duty cycle

def sef_fan_speed(cpu_temp):
    temp_lower_set = fan_temp;

    if (temp_unit == 'F'):
        temp_lower_set = (fan_temp - 32) * 5/9
    
    if fan_pwm:
        if cpu_temp < temp_lower_set:
            duty_cycle = 0
        elif cpu_temp > temp_higher_set:
            duty_cycle = max_fan_pwm
        else:
            duty_cycle = min_fan_pwm + (max_fan_pwm - min_fan_pwm) * (cpu_temp - temp_lower_set) / (temp_higher_set - temp_lower_set)
    else:
        if cpu_temp > temp_lower_set:
            duty_cycle = max_fan_pwm
        else:
            duty_cycle = 0

    fan_pwm_control.ChangeDutyCycle(duty_cycle)
    
def set_io(pin,val:bool):
    GPIO.setup(pin,GPIO.OUT)
    GPIO.output(pin,val)

def get_io(pin):
    GPIO.setup(pin,GPIO.IN)
    return GPIO.input(pin)

# endregion: io control

# region: rgb_strip init
try:
    strip = WS2812(LED_COUNT=16, LED_PIN=rgb_pin, LED_FREQ_HZ=rgb_pwm_freq*1000)
except Exception as e:
    log('rgb_strip init failed:\n%s'%e)
    rgb_switch = False

def rgb_show():
    log('rgb_show')
    try:
        if rgb_style in RGB_styles:
            log('rgb_show: %s'%rgb_style)
            strip.display(rgb_style, rgb_color, rgb_blink_speed, 255)
        else:
            log('rgb_style not in RGB_styles')
    except Exception as e:
        log(e,level='rgb_strip')

# endregion: rgb_strip init

def main():
    global fan_temp, power_key_pin, screen_off_time, rgb_color, rgb_pin
    global oled_stat
    time_start = time.time()
    power_key_flag = False
    power_timer = 0
    # rgb_strip thread
    if rgb_switch == True:
        rgb_thread = threading.Thread(target=rgb_show)
        rgb_thread.daemon = True
        rgb_thread.start()
    else:
        strip.clear()


    while True:
        # CPU temp
        CPU_temp_C = float(getCPUtemperature()) # celcius
        CPU_temp_F = float(CPU_temp_C * 1.8 + 32) # fahrenheit
        
        # fan control
        sef_fan_speed(float(CPU_temp_C))

        # oled control
        if oled_ok:
            if oled_stat == True:
                # CPU usage
                CPU_usage = float(getCPUuse())
                # clear draw buffer
                draw.rectangle((0,0,width,height), outline=0, fill=0)
                # get info
                # RAM
                RAM_stats = getRAMinfo()
                RAM_total = round(int(RAM_stats[0]) / 1024/1024,1)
                RAM_used = round(int(RAM_stats[1]) / 1024/1024,1)
                RAM_usage = round(RAM_used/RAM_total*100,1)
                # Disk information
                DISK_stats = getDiskSpace()
                DISK_total = str(DISK_stats[0])
                DISK_used = str(DISK_stats[1])
                DISK_perc = float(DISK_stats[3])
                # ip address
                ip = None
                IPs = getIP()

                if 'wlan0' in IPs and IPs['wlan0'] != None and IPs['wlan0'] != '':
                    ip = IPs['wlan0']
                elif 'eth0' in IPs and IPs['eth0'] != None and IPs['eth0'] != '':
                    ip = IPs['eth0']
                else:
                    ip = 'DISCONNECT'

                # display info
                ip_rect = Rect(48, 0, 81, 10)
                ram_info_rect = Rect(46, 17, 81, 10)
                ram_rect = Rect(46, 29, 81, 10)
                rom_info_rect = Rect(46, 41, 81, 10)
                rom_rect = Rect(46, 53, 81, 10)

                draw_text('CPU',6,0)
                draw.pieslice((0, 12, 30, 42), start=180, end=0, fill=0, outline=1)
                draw.pieslice((0, 12, 30, 42), start=180, end=int(180+180*CPU_usage*0.01), fill=1, outline=1)
                draw_text('{:^5.1f} %'.format(CPU_usage),2,27)
                # Temp
                if temp_unit == 'C':
                    draw_text('{:>4.1f} \'C'.format(CPU_temp_C),2,38)
                    draw.pieslice((0, 33, 30, 63), start=0, end=180, fill=0, outline=1)
                    draw.pieslice((0, 33, 30, 63), start=int(180-180*CPU_temp_C*0.01), end=180, fill=1, outline=1)
                elif temp_unit == 'F':
                    draw_text('{:>4.1f} \'F'.format(CPU_temp_F),2,38)
                    draw.pieslice((0, 33, 30, 63), start=0, end=180, fill=0, outline=1)
                    pcent = (CPU_temp_F-32)/1.8
                    draw.pieslice((0, 33, 30, 63), start=int(180-180*pcent*0.01), end=180, fill=1, outline=1)
                # RAM
                draw_text('RAM: {}/{} GB'.format(RAM_used,RAM_total),*ram_info_rect.coord())
                # draw_text('{:>5.1f}'.format(RAM_usage)+' %',92,0)
                draw.rectangle(ram_rect.rect(), outline=1, fill=0)
                draw.rectangle(ram_rect.rect(RAM_usage), outline=1, fill=1)
                # Disk
                draw_text('ROM: {}/{} GB'.format(DISK_used ,DISK_total), *rom_info_rect.coord())
                # draw_text('     ',72,32)
                # draw_text(''+' G',72,32)
                draw.rectangle(rom_rect.rect(), outline=1, fill=0)
                draw.rectangle(rom_rect.rect(DISK_perc), outline=1, fill=1)
                # IP
                draw.rectangle((ip_rect.x-13,ip_rect.y,ip_rect.x+ip_rect.width,ip_rect.height), outline=1, fill=1)
                draw.pieslice((ip_rect.x-25,ip_rect.y,ip_rect.x-3,ip_rect.height+10), start=270, end=0, fill=0, outline=0)
                draw_text(ip,*ip_rect.coord(),0)
                # draw the image buffer.
                oled.image(image)
                oled.display()

            # screen off timer
            if screen_always_on == False and (time.time()-time_start) > screen_off_time:
                oled.off()
                oled_stat = False

            # power key event
            if get_io(power_key_pin) == 0:
                # screen on
                if oled_ok and oled_stat == False:
                    oled.on()
                    oled_stat = True
                    time_start = time.time()
                # power off
                if power_key_flag == False:
                    power_key_flag = True
                    power_timer = time.time()
                elif (time.time()-power_timer) > 2:
                    oled.on()
                    draw.rectangle((0,0,width,height), outline=0, fill=0)
                    # draw_text('POWER OFF',36,24)
                    text_width, text_height = font_12.getsize('POWER OFF')
                    text_x = int((width - text_width)/2-1)
                    text_y = int((height - text_height)/2-1)
                    draw.text((text_x, text_y), text='POWER OFF', font=font_12, fill=1)
                    oled.image(image)
                    oled.display()
                    while not get_io(power_key_pin):
                        time.sleep(0.01)
                    log("POWER OFF")
                    oled_stat = False
                    oled.off()
                    os.system('sudo poweroff')
                    sys.exit(1)
            else:
                power_key_flag = False

        time.sleep(update_frequency)


class Rect:
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.x2 = self.x + self.width
        self.y2 = self.y + self.height

    def coord(self):
        return (self.x, self.y)
    def rect(self, pecent=100):
        return (self.x, self.y, self.x + int(self.width*pecent/100.0), self.y2)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log('error')
        log(e)
    finally:
        GPIO.cleanup()


