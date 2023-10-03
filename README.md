# portmgr
portmgr is a wrapper around docker-compose, which allows running typical commands on docker-compose.yml files recursively in multiple directories. Additionally, it shortens commands to a single letter each.

Let's say you have organized your compose files like this:
<pre>
docker/
├── reverse-proxy/
│   └── docker-compose.yml
├── public/
│   └── blog/
│       └── docker-compose.yml
├── private/
│   ├── nextcloud/
│   │   └── docker-compose.yml
│   └── gitlab/
│       └── docker-compose.yml
└── scripts
</pre>

You just add a `dckrsub.yml` in each parent folder like this:
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


### Prerequisites
The easiest way ist through [pip3](https://pypi.python.org/pypi/pip) (Ubuntu: `apt-get install python3-pip`):
* [docker-py](https://github.com/docker/docker-py): `pip3 install docker-py`
* [jsonschema](https://pypi.python.org/pypi/jsonschema): `pip3 install jsonschema`

### Installation
```
sudo pip install portmgr
```

Or build it from source (here using the latest commit on master branch)
```
sudo pip install https://github.com/Craeckie/portmgr.git
```

### Commands

```
  -u            Create and start containers (up)
  -p            Pull images (pull)
  -s            Stop services (stop)
  -d            Stop and remove containers (down)
  -a            Run shell in container (exec -it <service> sh)
  -b            Build images (build)
  -c            List containers (ps)
  -t            List processes in containers (top)
```
