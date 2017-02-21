# Server-configuration
Code and instructions for grader of my linux server configuration project

### IP address 
## 52.32.60.133
### URL: 
## http://ec2-52-32-60-133.us-west-2.compute.amazonaws.com/
### Key:
## linuxCourse
To log in, add the linuxCourse file to your machine's ssh folder
Then, in terminal run:
### ssh -i ~/.ssh/linuxCourse -p 2200 grader@52.32.60.133
The key's password is Lannister1

## Relevant Software installed:
Flask, Postgresql, apache2

## Security:
### Users:
There are two non-root sudoers student, and grader
### UFW and ports
the ssh port is changed from default port 22 to port 2200
only ports 2200(ssh), 8080(http), and 123(ntp) are up
### Software update
sudo apt-get udpade & 
sudo apt-get upgrade have both been run

# Helpfull Resources:
https://discussions.udacity.com/t/p5-how-i-got-through-it/15342
https://www.digitalocean.com/community/tutorials/how-to-add-and-delete-users-on-an-ubuntu-14-04-vps
https://www.digitalocean.com/community/tutorials/how-to-deploy-a-flask-application-on-an-ubuntu-vps
https://www.postgresql.org/docs/8.0/static/sql-alteruser.html
