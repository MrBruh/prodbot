# Deploy Setup (GCE Ubuntu VM)

## Prerequisites
- A bare git repo on the VM (e.g., `/home/deploy/discord-life-bot.git`)
- A working copy checkout (e.g., `/home/deploy/discord-life-bot`)
- A Python venv with deps installed

## Steps

### 1. Install the post-receive hook
```bash
cp deploy/post-receive /home/deploy/discord-life-bot.git/hooks/post-receive
chmod +x /home/deploy/discord-life-bot.git/hooks/post-receive
```
Edit the paths at the top of the script to match your environment.

### 2. Install the systemd service
```bash
sudo cp deploy/discord-life-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable discord-life-bot
sudo systemctl start discord-life-bot
```
Edit the paths in the service file to match your environment.

### 3. Allow passwordless restart
Add to sudoers so the deploy user can restart the service without a password:
```bash
sudo visudo -f /etc/sudoers.d/discord-life-bot
```
Add:
```
deploy ALL=(ALL) NOPASSWD: /bin/systemctl restart discord-life-bot
```

### 4. Create log directory
```bash
sudo mkdir -p /var/log/discord-life-bot
sudo chown deploy:deploy /var/log/discord-life-bot
```

### 5. Add the VM as a git remote
On your local machine:
```bash
git remote add production deploy@YOUR_VM_IP:/home/deploy/discord-life-bot.git
git push production master
```
