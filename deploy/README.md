# Deploy Setup (GCE Ubuntu VM)

## Prerequisites
- A bare git repo on the VM (e.g., `/home/deploy/prodbot.git`)
- A working copy checkout (e.g., `/home/deploy/prodbot`)
- A Python venv with deps installed

## Steps

### 1. Install the post-receive hook
```bash
cp deploy/post-receive /home/deploy/prodbot.git/hooks/post-receive
chmod +x /home/deploy/prodbot.git/hooks/post-receive
```
Edit the paths at the top of the script to match your environment.

### 2. Install the systemd service
```bash
sudo cp deploy/prodbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable prodbot
sudo systemctl start prodbot
```
Edit the paths in the service file to match your environment.

### 3. Allow passwordless restart
Add to sudoers so the deploy user can restart the service without a password:
```bash
sudo visudo -f /etc/sudoers.d/prodbot
```
Add:
```
deploy ALL=(ALL) NOPASSWD: /bin/systemctl restart prodbot
```

### 4. Create log directory
```bash
sudo mkdir -p /var/log/prodbot
sudo chown deploy:deploy /var/log/prodbot
```

### 5. Add the VM as a git remote
On your local machine:
```bash
git remote add production deploy@YOUR_VM_IP:/home/deploy/prodbot.git
git push production master
```
