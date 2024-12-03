# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License
"""Sort context by degree in descending order."""

import pandas as pd

import graphrag.index.graph.extractors.community_reports.schemas as schemas
from graphrag.query.llm.text_utils import num_tokens


def sort_context(
    local_context: list[dict],
    sub_community_reports: list[dict] | None = None,
    max_tokens: int | None = None,
    node_id_column: str = schemas.NODE_ID,
    node_name_column: str = schemas.NODE_NAME,
    node_details_column: str = schemas.NODE_DETAILS,
    edge_id_column: str = schemas.EDGE_ID,
    edge_details_column: str = schemas.EDGE_DETAILS,
    edge_degree_column: str = schemas.EDGE_DEGREE,
    edge_source_column: str = schemas.EDGE_SOURCE,
    edge_target_column: str = schemas.EDGE_TARGET,
    claim_id_column: str = schemas.CLAIM_ID,
    claim_details_column: str = schemas.CLAIM_DETAILS,
    community_id_column: str = schemas.COMMUNITY_ID,
) -> str:
    """Sort context by degree in descending order.

    If max tokens is provided, we will return the context string that fits within the token limit.
    """

    def _get_context_string(
        entities: list[dict],
        edges: list[dict],
        claims: list[dict],
        sub_community_reports: list[dict] | None = None,
    ) -> str:
        """Concatenate structured data into a context string."""
        contexts = []
        if sub_community_reports:
            sub_community_reports = [
                report
                for report in sub_community_reports
                if community_id_column in report
                and report[community_id_column]
                and str(report[community_id_column]).strip() != ""
            ]
            report_df = pd.DataFrame(sub_community_reports).drop_duplicates()
            if not report_df.empty:
                if report_df[community_id_column].dtype == float:
                    report_df[community_id_column] = report_df[
                        community_id_column
                    ].astype(int)
                report_string = (
                    f"----Reports-----\n{report_df.to_csv(index=False, sep=',')}"
                )
                contexts.append(report_string)

        entities = [
            entity
            for entity in entities
            if node_id_column in entity
            and entity[node_id_column]
            and str(entity[node_id_column]).strip() != ""
        ]
        entity_df = pd.DataFrame(entities).drop_duplicates()
        if not entity_df.empty:
            if entity_df[node_id_column].dtype == float:
                entity_df[node_id_column] = entity_df[node_id_column].astype(int)
            entity_string = (
                f"-----Entities-----\n{entity_df.to_csv(index=False, sep=',')}"
            )
            contexts.append(entity_string)

        if claims and len(claims) > 0:
            claims = [
                claim
                for claim in claims
                if claim_id_column in claim
                and claim[claim_id_column]
                and str(claim[claim_id_column]).strip() != ""
            ]
            claim_df = pd.DataFrame(claims).drop_duplicates()
            if not claim_df.empty:
                if claim_df[claim_id_column].dtype == float:
                    claim_df[claim_id_column] = claim_df[claim_id_column].astype(int)
                claim_string = (
                    f"-----Claims-----\n{claim_df.to_csv(index=False, sep=',')}"
                )
                contexts.append(claim_string)

        edges = [
            edge
            for edge in edges
            if edge_id_column in edge
            and edge[edge_id_column]
            and str(edge[edge_id_column]).strip() != ""
        ]
        edge_df = pd.DataFrame(edges).drop_duplicates()
        if not edge_df.empty:
            if edge_df[edge_id_column].dtype == float:
                edge_df[edge_id_column] = edge_df[edge_id_column].astype(int)
            edge_string = (
                f"-----Relationships-----\n{edge_df.to_csv(index=False, sep=',')}"
            )
            contexts.append(edge_string)

        return "\n\n".join(contexts)

    # sort node details by degree in descending order
    edges = []
    node_details = {}
    claim_details = {}

    for record in local_context:
        node_name = record[node_name_column]
        record_edges = record.get(edge_details_column, [])
        record_edges = [e for e in record_edges if not pd.isna(e)]
        record_node_details = record[node_details_column]
        record_claims = record.get(claim_details_column, [])
        record_claims = [c for c in record_claims if not pd.isna(c)]

        edges.extend(record_edges)
        node_details[node_name] = record_node_details
        claim_details[node_name] = record_claims

    edges = [edge for edge in edges if isinstance(edge, dict)]
    edges = sorted(edges, key=lambda x: x[edge_degree_column], reverse=True)

    sorted_edges = []
    sorted_nodes = []
    sorted_claims = []
    context_string = ""
    for edge in edges:
        source_details = node_details.get(edge[edge_source_column], {})
        target_details = node_details.get(edge[edge_target_column], {})
        sorted_nodes.extend([source_details, target_details])
        sorted_edges.append(edge)
        source_claims = claim_details.get(edge[edge_source_column], [])
        target_claims = claim_details.get(edge[edge_target_column], [])
        sorted_claims.extend(source_claims if source_claims else [])
        sorted_claims.extend(target_claims if source_claims else [])
        if max_tokens:
            new_context_string = _get_context_string(
                sorted_nodes, sorted_edges, sorted_claims, sub_community_reports
            )
            if num_tokens(new_context_string) > max_tokens:
                break
            context_string = new_context_string

    if context_string == "":
        return _get_context_string(
            sorted_nodes, sorted_edges, sorted_claims, sub_community_reports
        )

    return context_string


def sort_context_batch(
    local_contexts: pd.DataFrame,
    node_details_column: str = schemas.NODE_DETAILS,
    edge_details_column: str = schemas.EDGE_DETAILS,
    claim_details_column: str = schemas.CLAIM_DETAILS,
    community_id_column: str = schemas.COMMUNITY_ID,
    sub_community_reports: pd.DataFrame | None = None,
    max_tokens: int | None = None,
) -> pd.DataFrame:
    """Batch processing for community context strings, including subcommunity reports."""

    def generate_context(group):
        # Explode and deduplicate edges, claims, and nodes
        edges = pd.DataFrame(
            group[edge_details_column].explode().dropna().tolist()
        ).drop_duplicates()
        claims = pd.DataFrame(
            group[claim_details_column].dropna().tolist()
        ).drop_duplicates()
        nodes = pd.DataFrame(
            group[node_details_column].dropna().tolist()
        ).drop_duplicates()

        # Sort edges by degree descending
        if not edges.empty:
            edges = edges.sort_values(
                by=[schemas.EDGE_DEGREE, schemas.EDGE_ID],
                ascending=[False, True],
            )

        # Initialize context elements
        sorted_edges, sorted_nodes, sorted_claims = [], [], []
        contexts = []

        # Include sub-community reports
        if sub_community_reports is not None:
            reports = sub_community_reports[
                sub_community_reports[community_id_column] == group.name
            ]
            if not reports.empty:
                report_string = (
                    f"----Reports-----\n{reports.to_csv(index=False, sep=',')}"
                )
                contexts.append(report_string)

        # Incrementally add edges and their related data until token limit is reached
        context_string = ""
        for _, edge in edges.iterrows():
            source = edge[schemas.EDGE_SOURCE]
            target = edge[schemas.EDGE_TARGET]

            # Add source and target node details
            source_nodes = nodes[nodes[schemas.NODE_NAME] == source].to_dict("records")
            target_nodes = nodes[nodes[schemas.NODE_NAME] == target].to_dict("records")

            if len(source_nodes) > 0:
                sorted_nodes.append(source_nodes[0])
            if len(target_nodes) > 0:
                sorted_nodes.append(target_nodes[0])

            # Add claims for source and target
            if len(claims) > 0:
                related_claims = claims[
                    claims[schemas.CLAIM_SUBJECT].isin([source, target])
                ]
                if len(related_claims) > 0:
                    sorted_claims.extend(related_claims.to_dict("records"))

            # Add the edge itself
            sorted_edges.append(edge.to_dict())

            # Generate a new context string
            new_context_string = _get_context_string(
                sorted_nodes, sorted_edges, sorted_claims, contexts
            )
            if max_tokens and num_tokens(new_context_string) > max_tokens:
                break
            context_string = new_context_string

        context_string_len = num_tokens(context_string)
        return pd.Series({
            schemas.CONTEXT_STRING: context_string,
            schemas.CONTEXT_SIZE: context_string_len,
            schemas.CONTEXT_EXCEED_FLAG: context_string_len > max_tokens
            if max_tokens
            else False,
            schemas.ALL_CONTEXT: group[schemas.ALL_CONTEXT].tolist(),
        })

    def _get_context_string(
        entities: list[dict],
        edges: list[dict],
        claims: list[dict],
        existing_contexts: list[str],
    ) -> str:
        """Concatenate structured data into a context string."""
        contexts = (
            existing_contexts.copy()
        )  # Start with existing contexts (e.g., reports)
        if entities:
            entity_df = pd.DataFrame(entities).drop_duplicates()
            contexts.append(
                f"-----Entities-----\n{entity_df.to_csv(index=False, sep=',')}"
            )

        if claims:
            claim_df = pd.DataFrame(claims).drop_duplicates()
            contexts.append(
                f"-----Claims-----\n{claim_df.to_csv(index=False, sep=',')}"
            )

        if edges:
            edge_df = pd.DataFrame(edges).drop_duplicates()
            contexts.append(
                f"-----Relationships-----\n{edge_df.to_csv(index=False, sep=',')}"
            )

        return "\n\n".join(contexts)

    # Group by community and process in bulk
    context_results = local_contexts.groupby(community_id_column).apply(
        generate_context
    )

    # Return a DataFrame with the results
    return context_results.reset_index()
