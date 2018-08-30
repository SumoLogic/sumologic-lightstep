# sumologic-lightstep
This repository provides a configurable script to extract data from [Lightstep](https://lightstep.com) and ingest it as metrics into Sumo Logic.

## Support

The code in this repository has been developed in collaboration with the Sumo Logic community and is not supported via standard Sumo Logic Support channels. For any issues or questions please submit an issue directly on GitHub. The maintainers of this project will work directly with the community to answer any questions, address bugs, or review any requests for new features. 

## License
Released under Apache 2.0 License.

## Usage

This script can be run standalone or as a container.  In order to use the script, you need to provide a configuration file that defines the targets that the script should scrape for metrics.  The path to this configuration should be set in an environment variable `CONFIG_PATH`.  Below is an example configuration.

```json
{
  "sumo_http_url": "INSERT_SUMO_HTTP_SOURCE_URL_HERE",
  "lightstep_api_key": "INSERT_LIGHTSTEP_API_KEY_HERE",
  "lightstep_organization": "INSERT_LIGHTSTEP_ORGANIZATION_HERE",
  "targets": [
    {
      "project": "PROJECT_NAME",
      "searches": ["SEARCH_ID"],
      "percentiles": [50, 90, 99, 99.99]
    }
  ]
}
```

### Config Properties

| Key                      | Type   | Description                                               | Required  | Default |
| ---                      | -----  | -----------                                               | --------  | ------- |
| `sumo_http_url`          | String | This is the Sumo Logic HTTP URL to send the data to.      | Yes       | None    | 
| `lightstep_api_key`      | String | This is the Lightstep API Key.                            | Yes       | None    | 
| `lightstep_organization` | String | This is the Lightstep Organization.                       | Yes       | None    | 
| `global`                 | {}     | This is the global settings that apply to all targets.    | No        | None    |
| `targets`                | []     | A list of targets to scrape and send to Sumo Logic        | No        | None    |

### Global Properties
| Key                      | Type   | Description                                                                                  | Required  | Default |
| ---                      | -----  | -----------                                                                                  | --------  | ------- |
| `run_interval_seconds`   | int    | The interval in seconds in which the target should be scraped.                               | No        | 60      | 
| `batch_size`             | int    | The number of metrics per batch when posting to Sumo Logic.                                  | No        | 1000    | 
| `retries`                | int    | The number of times to retry the request when posting to Sumo Logic and there is an error.   | No        | 5       | 
| `backoff_factor`         | float  | A backoff factor to apply between attempts after the second try.                             | No        | .2      | 
| `source_category`        | String | The source category to assign to all data from every target, unless overridden in target.    | No        | None    | 
| `source_host`            | String | The source host to assign to all data from every target, unless overridden in target.        | No        | None    | 
| `source_name`            | String | The source name to assign to all data from every target, unless overridden in target.        | No        | None    | 
| `dimensions`             | String | Additional dimensions to assign to all data from every target, unless overridden in target.  | No        | None    | 
| `metadata`               | String | Additional metadata to assign to all data from every target, unless overridden in target.    | No        | None    | 


### Target Properties
| Key                       | Type          | Description                                                                                                  | Required  | Default | Overrides Global |
| ---                       | -----        | -----------                                                                                                   | --------  | ------- | ---------------- |
| `project`                 | String       | The Lightstep Project to scrape.                                                                              | Yes       | None    | N/A              |
| `resolution_ms`           | int          | The resolution in milliseconds.                                                                               | Yes       | 60000   | N/A              |
| `window_seconds`          | int          | The range of the time window.                                                                                 | Yes       | 60      | N/A              |
| `searches`                | \[String\]   | A list of searches to run in the project.                                                                     | Yes       | None    | N/A              |
| `percentiles`             | \[int/float\]| A list of percentiles to get from the search.   e.g. `[50, 90, 99, 99.99]`                                    | Yes       | None    | N/A              |
| `include_ops_counts`      | bool         | Whether or not to include the `ops-counts`                                                                    | No        | True    | N/A              |
| `include_error_counts`    | bool         | Whether or not to include the `error-counts`                                                                  | No        | True    | N/A              |
| `source_category`         | String       | The source category to assign to all data from every target.  Takes precedence over global setting.           | No        | None    | Yes              |
| `source_host`             | String       | The source host to assign to all data from every target.  Takes precedence over global setting.               | No        | None    | Yes              | 
| `source_name`             | String       | The source name to assign to all data from every target.  Takes precedence over global setting.               | No        | None    | Yes              | 
| `dimensions`              | String       | Additional dimensions to assign to all data from every target.  Takes precedence over global setting.         | No        | None    | Yes              | 
| `metadata`                | String       | Additional metadata to assign to all data from every target.  Takes precedence over global setting.           | No        | None    | Yes              |
| `run_interval_seconds`    | int          | The interval in seconds in which the target should be scraped.  Takes precedence over global setting.         | No        | None    | Yes              |

### Setup

#### Create a hosted collector and HTTP source in Sumo

In this step you create, on the Sumo service, an HTTP endpoint to receive your logs. This process involves creating an HTTP source on a hosted collector in Sumo. In Sumo, collectors use sources to receive data.

1. If you don’t already have a Sumo account, you can create one by clicking the **Free Trial** button on https://www.sumologic.com/.
2. Create a hosted collector, following the instructions on [Configure a Hosted Collector](https://help.sumologic.com/Send-Data/Hosted-Collectors/Configure-a-Hosted-Collector) in Sumo help. (If you already have a Sumo hosted collector that you want to use, skip this step.)  
3. Create an HTTP source on the collector you created in the previous step. For instructions, see [HTTP Logs and Metrics Source](https://help.sumologic.com/Send-Data/Sources/02Sources-for-Hosted-Collectors/HTTP-Source) in Sumo help. 
4. When you have configured the HTTP source, Sumo will display the URL of the HTTP endpoint. Make a note of the URL. You will use it when you configure the script to send data to Sumo. 

#### Deploy the script as you want to
The script can be configured with the following environment variables to be set.

| Variable            | Description                                                  | Required | DEFAULT VALUE    |
| --------            | -----------                                                  | -------- | -------------    |
| `CONFIG_PATH`       | The path to the configuration file.                          | YES      |  `./config.json` |
| `LOGGING_LEVEL`     | The logging level.                                           | NO       |  `INFO`          |

##### Running locally

  1. Clone this repo.
  2. Create the configuration file.  If config file is not in the same path as script, set CONFIG_PATH environment variable to config file path.
  3. Install [pipenv](https://docs.pipenv.org/#install-pipenv-today)
  4. Create local virtualenv with all required dependencies `pipenv install`
  5. Activate created virtualenv by running `pipenv shell`
  6. Run the script. `./sumologic_lightstep.py`
  
##### Running as a Docker Container

The script is packaged as a Docker Container, however the config file is still required and no default is provided.

##### Updating python dependencies
This project uses `Pipfile` and `Pipfile.lock` files to manage python dependencies and provide repeatable builds. To update packages you should run `pipenv update` or follow [pipenv upgrade workflow](https://docs.pipenv.org/basics/#example-pipenv-upgrade-workflow)