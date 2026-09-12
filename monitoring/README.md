# Monitoring

This Compose stack runs Prometheus and Grafana. Persistent data is stored on
the host at:

- `/mnt/cluster-workspace/data/prometheus`
- `/mnt/cluster-workspace/data/grafana`

## Start

Create the data directories and make them writable by the container users:

```sh
sudo mkdir -p /mnt/cluster-workspace/data/prometheus /mnt/cluster-workspace/data/grafana
sudo chown 65534:65534 /mnt/cluster-workspace/data/prometheus
sudo chown 472:472 /mnt/cluster-workspace/data/grafana
cp .env.example .env
chmod 600 .env
${EDITOR:-vi} .env
docker compose up -d
```

Open Grafana at <http://localhost:3000> and Prometheus at
<http://localhost:9090>. Grafana is preconfigured to use Prometheus; the
administrator username is `admin` and the password comes from `.env`.

To collect host metrics, run the node-exporter stack on each node. On the
monitoring host, start it with:

```sh
cd node-exporter
docker compose up -d --build
```

The Prometheus configuration already scrapes the monitoring host through
`host.docker.internal:9100` and `:9256`, plus `192.168.0.2:9100` and
`192.168.0.3:9100`. Apply configuration changes with:

```sh
docker compose restart prometheus
```

The Prometheus targets use the cluster addresses `192.168.0.2` for
`major-tom` and `192.168.0.3` for `ground-control`. The `node` labels preserve
the node names in Grafana legends.

The dashboard is in the intentionally named `dasboards/` directory. Deploy
all JSON dashboards through the Grafana API with:

```sh
sudo apt install jq
./scripts/deploy-dashboards.sh
```

`cluster-health-node-details.json` provides selectable detail views for
`major-tom`, `bowie`, and `ground-control`.

`slurm-overview.json` provides the Slurm scheduler and allocation overview
using metrics scraped by the `slurm` Prometheus job.

To continuously convert `tegrastats` output for node_exporter's textfile
collector, set `PROM_OUTPUT`, then run:

```sh
PROM_OUTPUT=/var/lib/node_exporter/textfile/tegrastats.prom \
python3.6 scripts/tegrastats_to_prom.py
```

The process panel requires `process-exporter`; node_exporter itself only
provides aggregate running and blocked process counts. NFS panels require the
NFS client/server statistics exposed by the node's kernel.

The default Prometheus retention is 30 days.
