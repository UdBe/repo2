import sys
from ruamel.yaml import YAML
import copy

# Initialize and configure the YAML object
def init_yaml():
    yaml = YAML()
    yaml.preserve_quotes = True  # Preserve quotes in strings
    yaml.indent(mapping=2, sequence=4, offset=2)  # Set indentation rules
    yaml.width = 4096  # Avoid line breaks for long strings
    yaml.default_flow_style = False  # Use block style for mappings and sequences
    return yaml

# Function to read YAML data from a file
def read_yaml(yaml, input_file):
    with open(input_file, 'r', encoding='utf8') as file:
        return yaml.load(file)

# Function to write YAML data to a file
def write_yaml(yaml, output_file, data):
    with open(output_file, 'w', encoding='utf8') as file:
        yaml.dump(data, file)

# Function to update the image_keys section for non-docker runtimes
def update_image_keys(runtime, repo_name):
    image_keys = runtime.get("image_keys", {})
    updated_image_keys = {}
    for key, value in image_keys.items():
        # Replace the image key with the repo_name
        updated_image_keys[repo_name] = value
    runtime['image_keys'] = updated_image_keys

# Function to modify the helm section
def update_helm(runtime):
    helm = runtime.get("helm", {})
    if helm:
        repo_url = helm.get("repo_url")
        if repo_url:
            # Remove 'http://' or 'https://' from the beginning of the URL
            if repo_url.startswith("https://"):
                repo_url = repo_url[len("https://"):]
            elif repo_url.startswith("http://"):
                repo_url = repo_url[len("http://"):]

            helm["repo_url"] = repo_url
            runtime["helm"] = helm

# Function to update the runtime if the type is "docker"
def process_docker_runtime(runtime, repo_name, base_imagepullsecret, is_repo1=False):
    # Identify the image_key (e.g., tika-ib) and convert it to rapidfort format or keep original for repo1
    image_key = next((key for key in runtime if key.endswith("-ib")), None)

    if image_key:
        # Create a new key, either with rapidfort/{image} or the original repo_name for repo1
        if is_repo1:
            new_key = repo_name  # Keep the original repo name for repo1
        else:
            new_key = f"rapidfort/{image_key.replace('-ib', '')}"
        runtime[new_key] = runtime.pop(image_key)

    # Add imagepullsecret and preserve_namespace to docker runtime
    runtime.update(base_imagepullsecret)

# Function to process the runtimes and add imagepullsecret to every runtime
def process_runtimes(data, repo_name, base_imagepullsecret, is_repo1=False):
    transformed_runtimes = []
    for runtime in data.get("runtimes", []):
        # Add the imagepullsecret to every runtime (both docker and non-docker)
        runtime.update(copy.deepcopy(base_imagepullsecret))

        if runtime.get("type") == "docker":
            process_docker_runtime(runtime, repo_name, base_imagepullsecret, is_repo1=is_repo1)
        else:
            update_image_keys(runtime, repo_name)
            update_helm(runtime)

        # Append the transformed runtime to the list
        transformed_runtimes.append(runtime)

    return transformed_runtimes

# Function to update repo_sets and remove the "output_repo" key
def update_repo_sets_exclude_output_repo(repo_sets):
    for repo_set in repo_sets:
        for repo_name, repo_data in repo_set.items():
            if "output_repo" in repo_data:
                # Remove the "output_repo" field
                del repo_data["output_repo"]

# Function to transform the data (common logic)
def transform_data(data, input_registry, output_registry, preserve_repo_sets=False, is_repo1=False):
    base_imagepullsecret = {
        "imagepullsecret": {
            "create": True,
            "filepath": "/tmp/docker/config.json",
            "name": "rf-regcred"
        },
        "preserve_namespace": True
    }

    # For repo1, use the original repo_name instead of rapidfort format
    if is_repo1:
        repo_name = next(iter(data.get("repo_sets", [{}])[0]))  # Use the original repo_name for repo1
    else:
        repo_name = f"rapidfort/{data['name'].replace('-ib', '')}"

    # Extract the input_base_tag and ensure it is properly quoted with double quotes
    repo_info = data.get("repo_sets", [{}])[0].values()
    input_base_tag = str(next(iter(repo_info), {}).get("input_base_tag", ""))
    input_base_tag = f'"{input_base_tag}"'

    # Process runtimes and apply modifications
    transformed_runtimes = process_runtimes(copy.deepcopy(data), repo_name, base_imagepullsecret, is_repo1=is_repo1)

    # If we want to preserve the original repo_sets, remove the "output_repo" field
    if preserve_repo_sets:
        repo_sets = copy.deepcopy(data.get("repo_sets", []))
        update_repo_sets_exclude_output_repo(repo_sets)  # Remove the "output_repo" field
    else:
        repo_sets = [
            {
                repo_name: {
                    "input_base_tag": input_base_tag
                }
            }
        ]

    return {
        "name": data["name"].replace("-ib", ""),
        "input_registry": {
            "registry": input_registry,
            "account": "ironbank-staging"
        },
        "output_registry": {
            "registry": output_registry,
            "account": "ironbank-staging"
        },
        "needs_common_commands": False,
        "repo_sets": repo_sets,
        "runtimes": transformed_runtimes,
    }

# transformation functions for each environment
def transform_data_mario(data):
    return transform_data(
        data, 
        input_registry="harbor-ib-mario.staging.dso.mil", 
        output_registry="harbor-ib-mario.staging.dso.mil"
    )

def transform_data_repo1(data):
    return transform_data(
        data, 
        input_registry="registry1.dso.mil", 
        output_registry="registry1.dso.mil", 
        preserve_repo_sets=True,  # Preserve repo_sets for Repo1
        is_repo1=True  # Ensure repo_name stays the same for Repo1
    )

def transform_data_zelda(data):
    return transform_data(
        data, 
        input_registry="harbor-ib-zelda.staging.dso.mil", 
        output_registry="harbor-ib-zelda.staging.dso.mil"
    )

# Function to generate the setup.sh script content
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

# Function to write the setup.sh file
def write_setup_script(data, gitlab_path):
    # Extract the first valid name field and remove '-ib' suffix
    component_name = None
    for key, value in data.items():
        if 'name' == key:
            image_name = data['name']
            component_name = image_name.replace('-ib', '')
            break 

    if component_name is None:
        print("No valid component name found in image.yml.")
        return

    # Generate the setup.sh script content
    setup_script_content = generate_setup_script(component_name)

    # Write the content to setup.sh
    with open(''f'{gitlab_path}/setup.sh', 'w') as setup_file:
        setup_file.write("#!/bin/bash\n\n")  # Shebang for bash
        setup_file.write(setup_script_content)

# Entry point of the script 
if __name__ == "__main__":

    if len(sys.argv) != 3:
        print("Usage: python create-gitlab-image-and-setup.py <source_image_yml> <gitlab_path>")
        sys.exit(1)

    image_yml = sys.argv[1]
    gitlab_path = sys.argv[2]

    yaml = init_yaml()
    
    # Read the image.yml file
    data = read_yaml(yaml, image_yml)

    # Transform the data using deep copies for each transformation
    mario_transformed_data = transform_data_mario(copy.deepcopy(data))
    write_yaml(yaml, f'{gitlab_path}/image-mario.yaml', mario_transformed_data)
    print("image-mario.yaml has been created")
    
    repo1_transformed_data = transform_data_repo1(copy.deepcopy(data))
    write_yaml(yaml, f'{gitlab_path}/image-repo1.yaml', repo1_transformed_data)
    print("image-repo1.yaml has been created")

    zelda_transformed_data = transform_data_zelda(copy.deepcopy(data))
    write_yaml(yaml, f'{gitlab_path}/image-zelda.yml', zelda_transformed_data)
    print("image-zelda.yaml has been created")

    # Generate setup.sh script from the component name
    write_setup_script(data, gitlab_path)
    print("setup.sh has been created.")
