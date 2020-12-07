# fury-web
Remote server for FURY online demo



# In case the port does not close when you stop the docker
Find out the process ID (PID) which is occupying the port number (e.g., 5955) you would like to free

    lsof -i :9000

Kill the process which is currently using the port using its PID

    kill PID