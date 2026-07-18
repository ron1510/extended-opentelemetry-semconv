
CREATE TABLE IF NOT EXISTS app_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	app_build_id TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS app_endpoint_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	service_name TEXT, 
	service_namespace TEXT, 
	http_request_method TEXT, 
	http_route TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS browser_document_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	browser_document_url_full TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS cicd_pipeline_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	cicd_pipeline_name TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS cicd_pipeline_run_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	cicd_pipeline_run_id TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS cicd_worker_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	cicd_worker_id TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS container_runtime_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	container_runtime_name TEXT, 
	container_runtime_version TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS gcp_gce_instance_group_manager_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	gcp_gce_instance_group_manager_name TEXT, 
	gcp_gce_instance_group_manager_zone TEXT, 
	gcp_gce_instance_group_manager_region TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_cluster_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_cluster_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_container_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_container_name TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_cronjob_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_cronjob_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_daemonset_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_daemonset_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_deployment_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_deployment_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_hpa_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_hpa_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_job_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_job_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_namespace_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_namespace_name TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_node_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_node_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_node_system_container_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_node_system_container_name TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_persistentvolume_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_persistentvolume_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_persistentvolumeclaim_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_persistentvolumeclaim_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_pod_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_pod_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_replicaset_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_replicaset_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_replicationcontroller_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_replicationcontroller_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_resourcequota_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_resourcequota_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_service_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_service_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS k8s_statefulset_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	k8s_statefulset_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS openshift_clusterquota_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	openshift_clusterquota_uid TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS process_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	process_pid TEXT, 
	process_creation_time TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS process_executable_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	process_executable_build_id_htlhash TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS process_runtime_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	process_runtime_name TEXT, 
	process_runtime_version TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS service_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	service_name TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS service_instance_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	service_instance_id TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS service_namespace_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	service_namespace TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS telemetry_distro_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	telemetry_distro_name TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS telemetry_sdk_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	telemetry_sdk_name TEXT, 
	telemetry_sdk_language TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS vcs_ref_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	vcs_ref_head_revision TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS vcs_repository_entities (
	entity_id TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	vcs_repository_url_full TEXT, 
	PRIMARY KEY (entity_id)
);


CREATE TABLE IF NOT EXISTS graph_edges (
	edge_id TEXT NOT NULL, 
	source_entity_id TEXT NOT NULL, 
	target_entity_id TEXT NOT NULL, 
	edge_type TEXT NOT NULL, 
	first_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	observations BIGINT DEFAULT 1 NOT NULL, 
	sources JSONB DEFAULT '{}'::jsonb NOT NULL, 
	attributes JSONB DEFAULT '{}'::jsonb NOT NULL, 
	PRIMARY KEY (edge_id)
);


CREATE TABLE IF NOT EXISTS graph_observations_seen (
	observation_id TEXT NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (observation_id)
);


CREATE TABLE IF NOT EXISTS graph_observation_errors (
	id BIGSERIAL NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	reason TEXT NOT NULL, 
	payload JSONB NOT NULL, 
	PRIMARY KEY (id)
);
