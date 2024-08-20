import yaml
from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO
import subprocess
import sys
import os
import shutil


def read_yaml(file_path):
    """Reads and returns image.yml data from a file."""
    try:
        with open(file_path, 'r') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        print(f"File {file_path} not found.")
        raise
    except yaml.YAMLError as exc:
        print(f"Error reading YAML file {file_path}: {exc}")
        raise

def transform_data_mario(data):
    """Transforms the input data to the desired output format."""
    repo_info = data.get("repo_sets", [{}])[0].values()  # Extract the first repo info safely

    repo_name = f"rapidfort/{data['name'].replace('-ib', '')}"

    # Extract the input_base_tag and ensure it is properly quoted with double quotes
    input_base_tag = str(next(iter(repo_info), {}).get("input_base_tag", ""))
    input_base_tag = f'"{input_base_tag}"'    

    # Define default values for k8s, docker_compose, and docker runtime types
    transformed_runtimes = []
    for runtime in data.get("runtimes", []):
        if runtime.get("type") == "k8s":
            # Process and format image_keys
            image_keys = {}
            for key, value in runtime.get("image_keys", {}).items():
                formatted_key = f"rapidfort/{key.replace('-ib', '')}"
                image_keys[formatted_key] = {
                    "registry": f'"{value.get("registry", "image.registry")}"',
                    "repository": f'"{value.get("repository", "image.repository")}"',
                    "tag": f'"{value.get("tag", "image.tag")}"'
                }

            # Override default k8s runtime values with values from image.yml
            updated_k8s_runtime = {
                "type": "k8s",
                "script": runtime.get("script", "k8s_coverage.sh"),
                "imagepullsecret": {
                    "filepath": runtime.get("imagepullsecret", {}).get("filepath", "/tmp/docker/config.json"),
                    "create": runtime.get("imagepullsecret", {}).get("create", True),
                    "name": runtime.get("imagepullsecret", {}).get("name", "rf-regcred"),
                },
                "preserve_namespace": runtime.get("preserve_namespace", True),
                "readiness_check_script": runtime.get("readiness_check_script", "health_check.sh"),
                "helm": {
                    "repo": runtime.get("helm", {}).get("repo", ""),
                    "repo_url": remove_https_prefix(runtime.get("helm", {}).get("repo_url", "")),
                    "chart": runtime.get("helm", {}).get("chart", ""),
                },
                "wait_time_sec": runtime.get("wait_time_sec", ""),
                "override_file": f'"{runtime.get("override_file", "overrides.yml")}"',
                "image_keys": image_keys,
                "readiness_wait_pod_name_suffix": runtime.get("readiness_wait_pod_name_suffix", [])
            }

            # Include any other fields from the runtime
            for key, value in runtime.items():
                if key not in updated_k8s_runtime:
                    updated_k8s_runtime[key] = value

            transformed_runtimes.append(updated_k8s_runtime)
        
        elif runtime.get("type") == "docker_compose":
            # Handle docker_compose runtimes
            image_keys = {}
            for key, value in runtime.get("image_keys", {}).items():
                formatted_key = f"rapidfort/{key.replace('-ib', '')}"
                image_keys[formatted_key] = {
                    "repository": f'"{value.get("repository", "")}"',
                    "tag": f'"{value.get("tag", "")}"'
                }
            updated_docker_compose_runtime = {
                "type": "docker_compose",
                "script": runtime.get("script", "dc_coverage.sh"),
                "compose_file": runtime.get("compose_file", "docker-compose.yml"),
                "imagepullsecret": {
                    "filepath": "/tmp/docker/config.json",
                    "create": True,
                    "name": "rf-regcred",
                },
                "preserve_namespace": runtime.get("preserve_namespace", True),
                "image_keys": image_keys
            }

            # Include any other fields from the runtime
            for key, value in runtime.items():
                if key not in updated_docker_compose_runtime:
                    updated_docker_compose_runtime[key] = value

            transformed_runtimes.append(updated_docker_compose_runtime)
       
        elif runtime.get("type") == "docker":
            # Handle docker runtimes
            docker_runtime = {
                "type": "docker",
                "script": runtime.get("script", "docker_coverage.sh"),
                "imagepullsecret": {
                    "filepath": "/tmp/docker/config.json",
                    "create": True,
                    "name": "rf-regcred",
                }
            }
            
            image_name = data["name"]
            if image_name in runtime:
                for key, value in runtime.get(image_name, {}).items():
                    if key not in {"imagepullsecret", "volumes", "entrypoint", "exec_command", "port"}:
                        formatted_key = f"rapidfort/{key.replace('-ib', '')}"

                # Create an entry in docker_runtime for the current image if necessary
                docker_runtime_image = {
                    "entrypoint": runtime[image_name].get("entrypoint", ""),
                    "exec_command": runtime[image_name].get("exec_command", "")
                }

                # Add volumes if they exist and include them in the docker_runtime_image dictionary
                volumes = runtime[image_name].get("volumes", {})
                if volumes:
                    docker_runtime_image["volumes"] = dict(volumes)

                # Add the entry only if it contains relevant data
                if any(docker_runtime_image.values()):
                    docker_runtime[f"rapidfort/{image_name}"] = docker_runtime_image

                # Include any other fields from the runtime
                for key, value in runtime.items():
                    if key not in docker_runtime:
                        docker_runtime[key] = value

                # Add the updated Docker runtime to the transformed runtimes list
                transformed_runtimes.append(docker_runtime)
    
    return {
        "name": data["name"].replace("-ib", ""),
        "input_registry": {
            "registry": "harbor-ib-mario.staging.dso.mil",
            "account": "ironbank-staging"
        },
        "output_registry": {
            "registry": "harbor-ib-mario.staging.dso.mil",
            "account": "ironbank-staging"
        },
        "repo_sets": [
            {
                repo_name: {
                    "input_base_tag": input_base_tag
                }
            }
        ],
        "needs_common_commands": False,
        "runtimes": transformed_runtimes,
    }

def transform_data_repo1(data):
    """Transforms the input data to the desired output format."""
    repo_info = data.get("repo_sets", [{}])[0].values()  # Extract the first repo info safely
    ironbank_source = data.get("repo_sets", [])
    first_repo_set = ironbank_source[0]
    repo_name = next(iter(first_repo_set), None)

    # Extract the input_base_tag and ensure it is properly quoted with double quotes
    input_base_tag = str(next(iter(repo_info), {}).get("input_base_tag", ""))
    input_base_tag = f'"{input_base_tag}"'    

    # Define default values for k8s, docker_compose, and docker runtime types
    transformed_runtimes = []
    for runtime in data.get("runtimes", []):
        if runtime.get("type") == "k8s":
            # Process and format image_keys
            image_keys = {}
            for key, value in runtime.get("image_keys", {}).items():
                formatted_key = f"rapidfort/{key.replace('-ib', '')}"
                image_keys[formatted_key] = {
                    "registry": f'"{value.get("registry", "image.registry")}"',
                    "repository": f'"{value.get("repository", "image.repository")}"',
                    "tag": f'"{value.get("tag", "image.tag")}"'
                }

            # Override default k8s runtime values with values from image.yml
            updated_k8s_runtime = {
                "type": "k8s",
                "script": runtime.get("script", "k8s_coverage.sh"),
                "imagepullsecret": {
                    "filepath": runtime.get("imagepullsecret", {}).get("filepath", "/tmp/docker/config.json"),
                    "create": runtime.get("imagepullsecret", {}).get("create", True),
                    "name": runtime.get("imagepullsecret", {}).get("name", "rf-regcred"),
                },
                "preserve_namespace": runtime.get("preserve_namespace", True),
                "readiness_check_script": runtime.get("readiness_check_script", "health_check.sh"),
                "helm": {
                    "repo": runtime.get("helm", {}).get("repo", ""),
                    "repo_url": remove_https_prefix(runtime.get("helm", {}).get("repo_url", "")),
                    "chart": runtime.get("helm", {}).get("chart", ""),
                },
                "wait_time_sec": runtime.get("wait_time_sec", ""),
                "override_file": f'"{runtime.get("override_file", "overrides.yml")}"',
                "image_keys": image_keys,
                "readiness_wait_pod_name_suffix": runtime.get("readiness_wait_pod_name_suffix", [])
            }

            # Include any other fields from the runtime
            for key, value in runtime.items():
                if key not in updated_k8s_runtime:
                    updated_k8s_runtime[key] = value

            transformed_runtimes.append(updated_k8s_runtime)
        
        elif runtime.get("type") == "docker_compose":
            # Handle docker_compose runtimes
            image_keys = {}
            for key, value in runtime.get("image_keys", {}).items():
                formatted_key = f"rapidfort/{key.replace('-ib', '')}"
                image_keys[formatted_key] = {
                    "repository": f'"{value.get("repository", "")}"',
                    "tag": f'"{value.get("tag", "")}"'
                }
            updated_docker_compose_runtime = {
                "type": "docker_compose",
                "script": runtime.get("script", "dc_coverage.sh"),
                "compose_file": runtime.get("compose_file", "docker-compose.yml"),
                "imagepullsecret": {
                    "filepath": "/tmp/docker/config.json",
                    "create": True,
                    "name": "rf-regcred",
                },
                "preserve_namespace": runtime.get("preserve_namespace", True),
                "image_keys": image_keys
            }

            # Include any other fields from the runtime
            for key, value in runtime.items():
                if key not in updated_docker_compose_runtime:
                    updated_docker_compose_runtime[key] = value

            transformed_runtimes.append(updated_docker_compose_runtime)
       
        elif runtime.get("type") == "docker":
            # Handle docker runtimes
            docker_runtime = {
                "type": "docker",
                "script": runtime.get("script", "docker_coverage.sh"),
                "imagepullsecret": {
                    "filepath": "/tmp/docker/config.json",
                    "create": True,
                    "name": "rf-regcred",
                }
            }
            
            image_name = data["name"]
            if image_name in runtime:
                for key, value in runtime.get(image_name, {}).items():
                    if key not in {"imagepullsecret", "volumes", "entrypoint", "exec_command", "port"}:
                        formatted_key = f"rapidfort/{key.replace('-ib', '')}"
                
                # Include volumes, entrypoint, and exec_command
                if "entrypoint" in runtime[image_name] or "exec_command" in runtime[image_name]:
                    docker_runtime.update({
                        repo_name: {
                            "entrypoint": runtime[image_name].get("entrypoint", ""),
                            "exec_command": runtime[image_name].get("exec_command", "")
                        }
                    })
                if "volumes" in runtime[image_name]:
                    docker_runtime["volumes"] = runtime[image_name].get("volumes", {})

                # Include any other fields from the runtime
                for key, value in runtime.items():
                    if key not in docker_runtime:
                        docker_runtime[key] = value

                # Add the updated Docker runtime to the transformed runtimes list
                transformed_runtimes.append(docker_runtime)
    
    return {
        "name": data["name"].replace("-ib", ""),
        "input_registry": {
            "registry": "registry1.dso.mil",
            "account": "ironbank-staging"
        },
        "output_registry": {
            "registry": "registry1.dso.mil",
            "account": "ironbank-staging"
        },
        "repo_sets": [
            {
                repo_name: {
                    "input_base_tag": input_base_tag
                }
            }
        ],
        "needs_common_commands": False,
        "runtimes": transformed_runtimes,
    }

def transform_data_zelda(data):
    """Transforms the input data to the desired output format."""
    repo_info = data.get("repo_sets", [{}])[0].values()  # Extract the first repo info safely

    repo_name = f"rapidfort/{data.get('name', '').replace('-ib', '')}"

    # Extract the input_base_tag and ensure it is properly quoted with double quotes
    input_base_tag = str(next(iter(repo_info), {}).get("input_base_tag", ""))
    input_base_tag = f'"{input_base_tag}"'

    # Define default values for k8s, docker_compose, and docker runtime types
    transformed_runtimes = []
    for runtime in data.get("runtimes", []):
        if runtime.get("type") == "k8s":
            # Process and format image_keys
            image_keys = {}
            for key, value in runtime.get("image_keys", {}).items():
                formatted_key = f"rapidfort/{key.replace('-ib', '')}"
                image_keys[formatted_key] = {
                    "registry": f'"{value.get("registry", "image.registry")}"',
                    "repository": f'"{value.get("repository", "image.repository")}"',
                    "tag": f'"{value.get("tag", "image.tag")}"'
                }

            # Handle readiness_wait_pod_name_suffix
            readiness_wait_pod_name_suffix = runtime.get("readiness_wait_pod_name_suffix", [])
            if not readiness_wait_pod_name_suffix:  # If list is empty
                readiness_wait_pod_name_suffix = [""]
            
            # Override default k8s runtime values with values from image.yml
            updated_k8s_runtime = {
                "type": "k8s",
                "script": runtime.get("script", "k8s_coverage.sh"),
                "imagepullsecret": {
                    "filepath": runtime.get("imagepullsecret", {}).get("filepath", "/tmp/docker/config.json"),
                    "create": runtime.get("imagepullsecret", {}).get("create", True),
                    "name": runtime.get("imagepullsecret", {}).get("name", "rf-regcred"),
                },
                "preserve_namespace": runtime.get("preserve_namespace", True),
                "readiness_check_script": runtime.get("readiness_check_script", "health_check.sh"),
                "helm": {
                    "repo": runtime.get("helm", {}).get("repo", ""),
                    "repo_url": remove_https_prefix(runtime.get("helm", {}).get("repo_url", "")),
                    "chart": runtime.get("helm", {}).get("chart", ""),
                },
                "wait_time_sec": runtime.get("wait_time_sec", ""),
                "override_file": f'"{runtime.get("override_file", "overrides.yml")}"',
                "image_keys": image_keys,
                "readiness_wait_pod_name_suffix": readiness_wait_pod_name_suffix
            }

            # Include any other fields from the runtime
            for key, value in runtime.items():
                if key not in updated_k8s_runtime:
                    updated_k8s_runtime[key] = value

            transformed_runtimes.append(updated_k8s_runtime)
        
        elif runtime.get("type") == "docker_compose":
            # Handle docker_compose runtimes
            image_keys = {}
            for key, value in runtime.get("image_keys", {}).items():
                formatted_key = f"rapidfort/{key.replace('-ib', '')}"
                image_keys[formatted_key] = {
                    "repository": f'"{value.get("repository", "")}"',
                    "tag": f'"{value.get("tag", "")}"'
                }
            updated_docker_compose_runtime = {
                "type": "docker_compose",
                "script": runtime.get("script", "dc_coverage.sh"),
                "compose_file": runtime.get("compose_file", "docker-compose.yml"),
                "imagepullsecret": {
                    "filepath": "/tmp/docker/config.json",
                    "create": True,
                    "name": "rf-regcred",
                },
                "preserve_namespace": runtime.get("preserve_namespace", True),
                "image_keys": image_keys
            }

            # Include any other fields from the runtime
            for key, value in runtime.items():
                if key not in updated_docker_compose_runtime:
                    updated_docker_compose_runtime[key] = value

            transformed_runtimes.append(updated_docker_compose_runtime)
       
        elif runtime.get("type") == "docker":
            # Handle docker runtimes
            docker_runtime = {
                "type": "docker",
                "script": runtime.get("script", "docker_coverage.sh"),
                "imagepullsecret": {
                    "filepath": "/tmp/docker/config.json",
                    "create": True,
                    "name": "rf-regcred",
                }
            }
            
            image_name = data.get("name", "")
            if image_name in runtime:
                image_data = runtime.get(image_name, {})
                if any(key in image_data for key in ["entrypoint", "exec_command"]):
                    docker_runtime.update({
                        f"rapidfort/{image_name}": {
                            "entrypoint": image_data.get("entrypoint", ""),
                            "exec_command": image_data.get("exec_command", "")
                        }
                    })
                if "volumes" in image_data:
                    docker_runtime["volumes"] = image_data.get("volumes", {})

                # Include any other fields from the runtime
                for key, value in runtime.items():
                    if key not in docker_runtime:
                        docker_runtime[key] = value

                # Add the updated Docker runtime to the transformed runtimes list
                transformed_runtimes.append(docker_runtime)
    
    return {
        "name": data.get("name", "").replace("-ib", ""),
        "input_registry": {
            "registry": "harbor-ib-zelda.staging.dso.mil",
            "account": "ironbank-staging"
        },
        "output_registry": {
            "registry": "harbor-ib-zelda.staging.dso.mil",
            "account": "ironbank-staging"
        },
        "repo_sets": [
            {
                repo_name: {
                    "input_base_tag": input_base_tag
                }
            }
        ],
        "needs_common_commands": False,
        "runtimes": transformed_runtimes,
    }

def remove_https_prefix(url):
    """Remove 'https://' prefix from a URL, if it exists."""
    if url.startswith("https://"):
        return url[len("https://"):]
    return url

def to_nice_yaml(value, indent=2):
    """Converts a Python object to a nicely formatted YAML string."""
    yaml = YAML()
    yaml.default_flow_style = False  # Ensures block style (not inline)
    yaml.indent(mapping=indent, sequence=indent, offset=indent)
    yaml.allow_unicode = True  # Allow Unicode characters in the output
    yaml.explicit_start = True  # Adds the explicit start marker "---"
    
    stream = StringIO()
    yaml.dump(value, stream)
    yaml_string = stream.getvalue()

    # Strip trailing spaces from each line
    yaml_string = "\n".join(line.rstrip() for line in yaml_string.splitlines())

    return yaml_string

def lint_yaml(yaml_string):
    """Lints the YAML content using yamllint."""
    try:
        result = subprocess.run(
            ['yamllint', '-'],  # Read from stdin
            input=yaml_string,
            text=True,
            capture_output=True
        )
        # We're linting the file but not checking or raising any issue. Make sure the YAML file is valid
    except Exception as e:
        # Handle the linting error silently
        print(f"Error during YAML linting: {e}")

def save_yaml_to_file(data, file_path):
    """Saves a Python object as a YAML file."""
    yaml_string = to_nice_yaml(data)  # Generate properly formatted YAML string
    lint_yaml(yaml_string)  # Lint YAML before saving
    with open(file_path, 'w') as file:
        file.write(yaml_string)

def generate_setup_script(component_name):
    """Generate setup.sh script content with the given component_name."""
    script_content = f"""
set -ex
SCRIPT_DIR="$(dirname "$(realpath -s "$0")")"
SCRIPT_ROOT_DIR="${{SCRIPT_DIR}}/../"
COMPONENT_NAME={component_name}

setup() {{
    pushd "${{SCRIPT_DIR}}"
        if test -f debug.sh;
        then
            echo "Running debug script"
            bash debug.sh
        else
            echo "Skipping debug script"
        fi
    popd
}}

cleanup() {{
    echo "Cleanup placeholder"
}}

start() {{
    pushd "${{SCRIPT_ROOT_DIR}}"
        echo "Starting setup scripts to install dependencies"
        bash common/scripts/setup.sh setup
        echo "Finished setup scripts"

        echo "Starting generating stub image"
        python3 common/orchestrator/main.py stub $COMPONENT_NAME \
            --namespace="${{RAPIDFORT_NAMESPACE}}" --image-to-scan="${{IMAGE_TO_SCAN}}"
        echo "Finished generating stub image"

        echo "Starting coverage tests"
        python3 common/orchestrator/main.py stub_coverage $COMPONENT_NAME \
            --namespace="${{RAPIDFORT_NAMESPACE}}" --image-to-scan="${{IMAGE_TO_SCAN}}"
        echo "Finished coverage tests"

        echo "Starting cleanup"
        bash common/scripts/setup.sh cleanup
        echo "Finished cleanup"
    popd
}}

case "${{1}}"
in
    ("setup") setup ;;
    ("cleanup") cleanup ;;
    ("start") start ;;
    (*) echo "$0 [ setup | cleanup | start ]" ;;
esac
    """
    return script_content

if __name__ == "__main__":

    if len(sys.argv) != 3:
        print("Usage: python create-gitlab-images-and-setup.py <source_image_yml> <gitlab_path>")
        sys.exit(1)

    image_yml = sys.argv[1]
    gitlab_path = sys.argv[2]

    # Read the image.yml file
    data = read_yaml(image_yml)

    # Generate and save all three output files
    transformed_data_mario = transform_data_mario(data)
    save_yaml_to_file(transformed_data_mario, f'{gitlab_path}/image-mario.yaml')
    print("image-mario.yaml has been created")

    transformed_data_repo1 = transform_data_repo1(data)
    save_yaml_to_file(transformed_data_repo1, f'{gitlab_path}/image-repo1.yaml')
    print("image-repo1.yaml has been created")

    transformed_data_zelda = transform_data_zelda(data)
    save_yaml_to_file(transformed_data_zelda, f'{gitlab_path}/image-zelda.yaml')
    print("image-zelda.yaml has been created")

    # Extract the first valid name field and remove '-ib' suffix
    component_name = None
    for key, value in data.items():
        if 'name'== key:
            image_name = data['name']
            component_name = image_name.replace('-ib', '')
            break  # Assuming you only need the first valid name

    if component_name is None:
        print("No valid component name found in image.yml.")

    # Generate the setup.sh script content
    setup_script_content = generate_setup_script(component_name)

    # Write the content to setup.sh
    with open(f'{gitlab_path}/setup.sh', 'w') as setup_file:
        setup_file.write("#!/bin/bash\n\n")  # Shebang for bash
        setup_file.write(setup_script_content)

    print("setup.sh has been created.")
