#!/usr/bin/env python

import arrow
import click
import gzip
import json
import logging
import os
import requests

from apscheduler.schedulers.blocking import BlockingScheduler
from json.decoder import JSONDecodeError
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from voluptuous import (
    Schema,
    Url,
    Required,
    MultipleInvalid,
    All,
    Range,
    Length,
    Coerce,
)

logging_level = os.environ.get("LOGGING_LEVEL", "INFO")
logging_format = "%(asctime)s [level=%(levelname)s] [thread=%(threadName)s] [module=%(module)s] [line=%(lineno)d]: %(message)s"
logging.basicConfig(level=logging_level, format=logging_format)
log = logging.getLogger(__name__)


def batches(iterator, batch_size: int):
    for i in range(0, len(iterator), batch_size):
        yield "\n".join(iterator[i:i + batch_size]).encode("utf-8")


class SumoHTTPAdapter(HTTPAdapter):
    CONFIG_TO_HEADER = {
        "source_category": "X-Sumo-Category",
        "source_name": "X-Sumo-Name",
        "source_host": "X-Sumo-Host",
        "metadata": "X-Sumo-Metadata",
        "dimensions": "X-Sumo-Dimensions",
    }

    def __init__(self, config, max_retries, **kwds):
        self._prepared_headers = self._prepare_headers(config)
        super().__init__(max_retries=max_retries, **kwds)

    def add_headers(self, request, **kwds):
        for k, v in self._prepared_headers.items():
            request.headers[k] = v

    def _prepare_headers(self, config):
        headers = {}
        for config_key, header_name in self.CONFIG_TO_HEADER.items():
            if config_key in config:
                headers[header_name] = config[config_key]
        return headers


class LightstepExtractor:
    def __init__(self, project: str, config: dict):
        self._base_url = "https://api.lightstep.com/public/v0.1/Sumologic/projects/"
        self._batch_size = config["batch_size"]
        self._config = config
        self._project = project
        self._lightstep_session = None
        self._sumo_session = None

        self._lightstep_session = requests.Session()

        retries = config["retries"]
        sumo_retry = Retry(
            total=retries,
            read=retries,
            method_whitelist=frozenset(["POST", *Retry.DEFAULT_METHOD_WHITELIST]),
            connect=retries,
            backoff_factor=config["backoff_factor"],
        )
        self._sumo_session = requests.session()
        adapter = SumoHTTPAdapter(config=config, max_retries=sumo_retry)
        self._sumo_session.mount("http://", adapter)
        self._sumo_session.mount("https://", adapter)

    def _generate_url(self, search: str):
        url = "{0}{1}/searches/{2}/timeseries".format(
            self._base_url, self._config["project"], search
        )
        return url

    def _generate_url_params(self):
        window = self._config["window_seconds"]
        oldest = (
            arrow.utcnow()
            .replace(seconds=-window)
            .floor("minute")
            .format("YYYY-MM-DDTHH:mm:ssZZ")
        )
        youngest = arrow.utcnow().floor("minute").format("YYYY-MM-DDTHH:mm:ssZZ")
        params = {
            "resolution-ms": self._config["resolution_ms"],
            "percentile": self._config["percentiles"],
            "oldest-time": oldest,
            "youngest-time": youngest,
            "include-ops-counts": int(self._config["include_ops_counts"]),
            "include-error-counts": int(self._config["include_error_counts"]),
        }
        return params

    def run(self):
        all_metrics = []
        for search in self._config["searches"]:
            log.info(f"getting data for search {search}")
            resp = self._lightstep_session.get(
                url=self._generate_url(search=search),
                params=self._generate_url_params(),
                headers={"Authorization": "Bearer {0}".format(self._config["lightstep_api_key"])},
            )
            resp.raise_for_status()
            metrics = self._parse_metrics(resp.content)
            log.info(f"got back {len(metrics)} metrics")
            all_metrics.extend(metrics)
        for batch in batches(all_metrics, self._batch_size):
            log.info("sending batch to sumo logic")
            resp = self._sumo_session.post(
                self._config["sumo_http_url"],
                data=gzip.compress(data=batch, compresslevel=1),
                headers={
                    "Content-Type": "application/vnd.sumologic.carbon2",
                    "Content-Encoding": "gzip"
                },
            )
            resp.raise_for_status()

    def _parse_metrics(self, timeseries):
        metrics = []
        parsed = json.loads(timeseries)
        for index in range(parsed["data"]["attributes"]["points-count"]):
            timestamp = arrow.get(
                parsed["data"]["attributes"]["time-windows"][index]["youngest-time"]
            ).timestamp
            project = self._config["project"]
            id = parsed["data"]["id"]
            res = parsed["data"]["attributes"]["resolution-ms"]
            if self._config["include_error_counts"]:
                value = parsed["data"]["attributes"]["error-counts"][index]
                metrics.append(
                    f"metric=error-counts project={project} id={id} resolution-ms={res}  {value} {timestamp}"
                )
            if self._config["include_ops_counts"]:
                value = parsed["data"]["attributes"]["ops-counts"][index]
                metrics.append(
                    f"metric=ops-counts project={project} id={id} resolution-ms={res}  {value} {timestamp}"
                )
            for latency in parsed["data"]["attributes"]["latencies"]:
                pct = latency["percentile"]
                value = latency["latency-ms"][index]
                metrics.append(
                    f"metric=latency-ms project={project} id={id} resolution-ms={res} percentile={pct}  {value} {timestamp}"
                )
        return metrics


global_config_schema = Schema(
    {
        Required("run_interval_seconds", default=60): All(int, Range(min=1)),
        Required("batch_size", default=1000): All(int, Range(min=1)),
        Required("retries", default=5): All(int, Range(min=1, max=20)),
        Required("backoff_factor", default=0.2): All(float, Range(min=0)),
        "source_category": str,
        "source_host": str,
        "source_name": str,
        "dimensions": str,
        "metadata": str,
    }
)

target_config_schema = global_config_schema.extend(
    {
        Required("project"): str,
        Required("resolution_ms", default=60000): All(int, Range(min=60000)),
        Required("window_seconds", default=60): All(int, Range(min=60)),
        Required("searches"): list([str]),
        Required("percentiles"): list([Coerce(float)]),
        Required("include_ops_counts", default=True): bool,
        Required("include_error_counts", default=True): bool,
        # repeat keys from global to remove default values
        "run_interval_seconds": All(int, Range(min=1)),
        "batch_size": All(int, Range(min=1)),
        "retries": All(int, Range(min=1, max=20)),
        "backoff_factor": All(float, Range(min=0)),
    }
)

config_schema = Schema(
    {
        Required("sumo_http_url"): Url(),
        Required("lightstep_api_key"): str,
        Required("global", default={}): global_config_schema,
        Required("targets"): All(Length(min=1), [target_config_schema]),
    }
)


def validate_config_file(ctx, param, value):
    try:
        return config_schema(json.load(value))
    except JSONDecodeError as e:
        raise click.BadParameter(str(e), ctx=ctx, param=param)
    except MultipleInvalid as e:
        raise click.BadParameter(e.msg, ctx=ctx, param=param, param_hint=e.path)


@click.command()
@click.argument(
    "config",
    envvar="CONFIG_PATH",
    callback=validate_config_file,
    type=click.File("r"),
    default="config.json",
)
def extract_data(config):
    scheduler = BlockingScheduler(timezone="UTC")
    for target_config in config["targets"]:
        scheduler_config = {
            "sumo_http_url": config["sumo_http_url"],
            "lightstep_api_key": config["lightstep_api_key"],
        }
        scheduler_config.update(target_config)
        for k, v in config["global"].items():
            scheduler_config.setdefault(k, v)
        project = target_config["project"]
        lightstep = LightstepExtractor(project, scheduler_config)
        scheduler.add_job(
            func=lightstep.run,
            name=project,
            id=project,
            trigger="interval",
            seconds=scheduler_config["run_interval_seconds"],
        )
    scheduler.start()


if __name__ == "__main__":
    extract_data()
