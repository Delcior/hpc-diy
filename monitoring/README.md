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

To collect node metrics, add a `nodes` scrape job to
`prometheus/prometheus.yml` with the hostnames or IP addresses of the nodes
running `node_exporter`, then apply the configuration:

```sh
docker compose restart prometheus
```

The default Prometheus retention is 30 days.
