#!/usr/bin/env python3
import os
import sys
import time
sys.path.append('./pironman')
from app_info import __app_name__, __version__, username, user_home, config_file

# user and username home directory

errors = []

avaiable_options = ['-h', '--help', '--no-dep']

usage = '''
Usage:
    sudo python3 install.py [option]

Options:
               --no-dep    Do not download dependencies
    -h         --help      Show this help text and exit
'''


APT_INSTALL_LIST = [ 
    # 'python3-pip',
    'python3-smbus',
    'i2c-tools',
    'libopenjp2-7 ',
    'libtiff5',

]


PIP_INSTALL_LIST = [
    'rpi-ws281x',
    'pillow',
]


def run_command(cmd=""):
    import subprocess
    p = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result = p.stdout.read().decode('utf-8')
    status = p.poll()
    return status, result


def do(msg="", cmd=""):
    print(" - %s... " % (msg), end='', flush=True)
    status, result = run_command(cmd)
    if status == 0 or status == None or result == "":
        print('Done')
    else:   
        print('\033[1;35mError\033[0m')
        errors.append("%s error:\n  Status:%s\n  Error:%s" %
                      (msg, status, result))


def install(): 

    options = []
    if len(sys.argv) > 1:
        options = sys.argv[1:]
        for opt in options:
            if opt not in avaiable_options:
                print("Option {} is not found.".format(opt))
                print(usage)
                quit()
        if "-h" in options or "--help" in options:
            print(usage)
            quit()
    #  
    print("%s install process starts"%__app_name__)
    if "--no-dep" not in options:    
        do(msg="update apt",
            cmd='sudo apt update -y'
        )
        do(msg="update pip3",
            cmd='python3 -m pip install --upgrade pip'
        )
        print("Install dependency")
        for dep in APT_INSTALL_LIST:
            do(msg="install %s"%dep,
                cmd='sudo apt install %s -y'%dep)
        for dep in PIP_INSTALL_LIST:
            do(msg="install %s"%dep,
                cmd='sudo pip3 install %s'%dep)
    #
    do(msg="enable i2c",
        cmd='sudo raspi-config nonint do_i2c 0'
    )   
    #
    print('create WorkingDirectory')    
    do(msg="create /opt",
        cmd='sudo mkdir -p /opt'
        +' && sudo chmod 774 /opt'
        +' && sudo chown %s:%s /opt'%(username, username) 
    )       
    do(msg="create dir",
        cmd='sudo mkdir -p /opt/%s'%__app_name__
        +' && sudo chmod 774 /opt/%s'%__app_name__  
        +' && sudo chown %s:%s /opt/%s'%(username, username, __app_name__) 
    )
    #
    do(msg='copy service file',
        cmd='sudo cp -rpf ./bin/%s.service /usr/lib/systemd/system/%s.service '%(__app_name__, __app_name__)
        +' && sudo cp -rpf ./bin/%s /usr/local/bin/%s'%(__app_name__, __app_name__)
        +' && sudo cp -rpf ./%s/* /opt/%s/'%(__app_name__, __app_name__)
    ) 
    do(msg="add excutable mode for service file",
        cmd='sudo chmod +x /usr/lib/systemd/system/%s.service'%__app_name__
        +' && sudo chmod +x /usr/local/bin/%s'%__app_name__
        +' && sudo chmod -R 774 /opt/%s'%__app_name__
        +' && sudo chown -R %s:%s /opt/%s'%(username, username, __app_name__)
    ) 
    #
    print('create config file')
    if not os.path.exists('%s/.config'%user_home):
        os.mkdir('%s/.config'%user_home)
        os.popen('sudo chmod 774 %s/.config'%user_home)  
        run_command('sudo  chown %s:%s %s/.config'%(username, username, user_home))    
    do(msg='copy config file',
        cmd='sudo mkdir -p %s/.config/%s '%(user_home, __app_name__)
        +' && sudo cp -rpf ./config.txt %s/.config/%s/config.txt '%(user_home, __app_name__)
        +' && sudo chown  -R %s:%s %s/.config/%s'%(username, username, user_home, __app_name__)
    )
    #     
    print('check startup files')
    run_command('sudo systemctl daemon-reload')
    status, result = run_command('sudo systemctl list-unit-files|grep %s'%__app_name__)
    if status==0 or status==None and result.find('%s.service'%__app_name__) != -1:
        do(msg='enable the service to auto-start at boot',
            cmd='sudo systemctl enable %s.service'%__app_name__
        )
    else:
        errors.append("%s error:\n  Status:%s\n  Error:%s" %
                      ('check startup files ', status, result))                  
    #
    # do(msg='run the service',
    #     cmd='sudo systemctl restart %s.service'%__app_name__
    # )
    time.sleep(0.1)
    do(msg='run the service',
        cmd='sudo pironman restart'
    )

    if len(errors) == 0:
        print("Finished.")
        print("You can manually clear the installation files now.")
    else:
        print('\n\n\033[1;35mError happened in install process:\033[0m')
        for error in errors:
            print(error)
        print("Try to fix it yourself, or contact service@sunfounder.com with this message")
        sys.exit(1)    

    
if __name__ == "__main__":
    try:
       install() 
    except KeyboardInterrupt:
        print("\n\nCanceled.")
