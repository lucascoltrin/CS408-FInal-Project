# SF Performance (Hello World)

## Install these first
Python 3.10+, PostgreSQL (running).
- Ubuntu: `sudo apt install python3 python3-venv postgresql`
- macOS: `brew install python postgresql@16 && brew services start postgresql@16`

## Run locally
    ./start.sh          # then open http://127.0.0.1:8000/

## Server setup (once)
    scp -i ~/keys/mykey.pem -r deploy ubuntu@<PUBLIC-IP>:~
    ssh -i ~/keys/mykey.pem ubuntu@<PUBLIC-IP>
    sudo bash deploy/setup-ec2.sh

## Deploy (every time, from your laptop)
    ./deploy/deploy.sh -h <PUBLIC-IP> -i ~/keys/mykey.pem

## Prove it starts on boot
    ssh -i ~/keys/mykey.pem ubuntu@<PUBLIC-IP> sudo reboot
    # wait ~1 minute, then load http://<PUBLIC-IP>/

## Staff login (owner dashboard)
There is no public sign-up for staff. Create the owner login on the server (or locally) and you will be prompted for a password:

    cd /opt/sfperformance
    ./venv/bin/python manage.py create_employee --username owner --name "Owner"

Reset a forgotten password with `--reset-password`. Staff log in at `/staff/login/` (there is no link to it on the public site) and land on `/dashboard/`.
