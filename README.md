# portmgr
portmgr is a wrapper around docker-compose, which allows running typical commands on docker-compose.yml files recursively in multiple directories. Additionally, it shortens commands to a single letter.

Let's say you have organized your compose files like this, you just add a `dckrsub.yml` in each parent folder:
<pre>
docker/
├── <b>dckrsub.yml</b>
├── reverse-proxy/
│   └── docker-compose.yml
├── storage
│   ├── <b>dckrsub.yml</b>
│   ├── nextcloud/
│   │   └── docker-compose.yml
│   └── immich/
│       └── docker-compose.yml
└── scripts
</pre>

Each `dckrsub.yml` has a list of subdirectories, which portmgr should decend into.
For example, the `dckrsub.yml` in `docker/` might look like this:
```yaml
- reverse-proxy
- storage
```

And the `dckrsub.yml` in `docker/storage/` is like this:
```yaml
- nextcloud
- immich
```

Now, if you run `portmgr u` in `docker/` it will decend into all the directories defined in each `dckrsub.yml` and run `docker compose up -d`. 

portmgr starts from the current directory, so when running it in `docker/storage/`, it will run `docker compose` only in `nextcloud/` and `immich/`. You can also use it in a directory with a `docker-compose.yml` as a shortener for docker-compose commands.

### Commands
The following commands are available.  You can leave out the preceding `-` and combine multiple commands. 
The respective docker-compose commands are in brackets.

```
  -u            Create and start containers (up)
  -p            Pull images (pull)
  -s            Stop services (stop)
  -d            Stop and remove containers (down)
  -l            Show container logs (logs)
  -a            Run shell in container (exec -it <service> sh)
  -b            Build images (build)
  -c            List containers (ps)
  -t            List processes in containers (top)
  -r            Build and push to registry (build, push)
  -v            Scan container images for vulnerabilities
```

For example `portmgr dul`, runs docker compose with `down`, `up` and `logs`, thus stopping, removing and starting all containers and then showing the logs.

### Installation
```
sudo pip install portmgr
```

Or build it from source (here using the latest commit on master branch)
```
sudo pip install https://github.com/Craeckie/portmgr.git
```


