# 3 Steps to building
Make sure docker desktop is running and you have tested the build locally.

1. `docker build --tag host2mqtt .`
2. `docker image tag host2mqtt denizenn\host2mqtt`
3. `docker push denizenn\host2mqtt`