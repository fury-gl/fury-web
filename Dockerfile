# To build this image:
#
# sudo docker build -t fury-egl-py3 .
#
# To build the image using a different base image:
#
# sudo docker build --build-arg BASE_IMAGE=pvw-v5.7.1-osmesa-py3 -t fury-egl-py3 .
#
# The following will configure all EXPOSED ports to be mapped to random
# ports on the host.  After which, you will use "docker port <container>"
# to find out the mapping.
#
# sudo docker run --runtime=nvidia -P -ti fury-egl-py3
#
# The following is specific about which container ports get mapped to which
# host ports.  In this case port 80 in the container is mapped to port 8081
# on the host:
#
# sudo docker run --runtime=nvidia -p 127.0.0.1:8081:80 -ti fury-egl-py3
#
# Or, to customize the protocol and hostname used in the sessionURL returned
# by the launcher, you can provide an extra argument after the image
# name:
#
# sudo docker run --runtime=nvidia -p 127.0.0.1:8081:80 -ti fury-egl-py3 "wss://www.example.com"
#
# In order to run the container with a bash shell instead (for debugging):
#
# sudo docker run --runtime=nvidia --entrypoint=bash -ti fury-egl-py3
#
# To run the container mounting a host directory for access by the container:
#
# sudo docker run --runtime=nvidia -v /data/my_folder:/data -p 127.0.0.1:8081:80 -ti fury-egl-py3
#
# To debug when container is running:
# docker ps (to get the name of the running container)
# docker exec -it container_name bash
#
# Check docker apache
# docker exec -it container_name cat /etc/apache2/sites-available/001-pvw.conf
# docker exec -it container_name cat /opt/launcher/config-template.json
# docker exec -it container_name cat /opt/launcher/config.json
#
# Some useful links:
# - https://hub.docker.com/r/kitware/paraview
# - https://github.com/Kitware/paraviewweb/tree/master/tools/docker/paraviewweb
#
# docker run -v /Users/koudoro/Software/fury-web:/pvw -p 127.0.0.1:8081:80 -e "SERVER_NAME=localhost:8081" -e "PROTOCOL=ws" -ti furyweb-0.4.0
#
# add the option "--gpu all" or --runtime=nvidia when you have nvidia-docker install on a Linux based system


ARG BASE_IMAGE=kitware/paraview:pvw-v5.7.1-osmesa-py3
# ARG BASE_IMAGE=kitware/paraview:pvw-v5.7.1-egl-py3

FROM ${BASE_IMAGE}

# Copy the launcher config template
COPY launcher/config.json /opt/launcher/config-template.json

#
# Now w run this script which will update the apache vhost file.  We use bash
# instead of "sh" due to the use of "read -d" in the script.  Also, it is bash, not
# docker which manages the env variable interpolation, so we must use bash if we
# want that convenience.
#
# To add more endpoints, simply add more pairs of arguments beyond "visualizer" and
# "/opt/paraview/.../www".
#
# RUN ["/opt/paraviewweb/scripts/addEndpoints.sh", \
#   "fury", "/pvw/apps/fury/www" \
# ]
# RUN ["/opt/paraviewweb/scripts/addEndpoints.sh", \
#   "horizon", "/pvw/apps/horizon/www" \
# ]
# RUN ["/opt/paraviewweb/scripts/addEndpoints.sh", \
#   "demo", "/pvw/apps/demo/www" \
# ]
#
# Workaround for buggy scipy
RUN mv /opt/paraview/lib/python3.6/site-packages/scipy /opt/paraview/lib/python3.6/site-packages/buggy_scipy
# install git for working with branch
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y git

# Start the container
ENTRYPOINT ["/opt/paraviewweb/scripts/server.sh"]