"""
Coordinator API for running games on-demand (e.g. for the web editor
and tutorial).
"""
import datetime
import io
import re

import flask
import google.cloud.exceptions as gcloud_exceptions
import google.cloud.storage as gcloud_storage

from .. import model, ondemand, util

from . import util as web_util
from .blueprint import web_api

@web_api.route("/ondemand/<int:intended_user>", methods=["GET"])
@util.cross_origin(methods=["GET", "POST", "PUT"])
@web_util.requires_login(accept_key=False)
def check_ondemand(intended_user, *, user_id):
    if user_id != intended_user:
        raise web_util.user_mismatch_error(
            message="Cannot check ondemand game for another user.")

    # Only return certain fields from the task
    task = ondemand.check_status(user_id)
    if task:
        result = {}

        for field_name in ("environment_parameters",
                           "compile_error",
                           "error_log",
                           "bot_log",
                           "game_output",
                           "opponents",
                           "objective",
                           "snapshots",
                           "crashed",
                           "status"):
            if field_name in task:
                result[field_name] = task[field_name]

        return util.response_success(result)

    return util.response_success({
        "status": "none",
    })


# Validate bot names
BOT_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9-_]*$")


@web_api.route("/ondemand/<int:intended_user>", methods=["POST"])
@util.cross_origin(methods=["GET", "POST", "PUT"])
@web_util.requires_login(accept_key=False)
def create_ondemand(intended_user, *, user_id):
    if user_id != intended_user:
        raise web_util.user_mismatch_error(
            message="Cannot start ondemand game for another user.")

    if "opponents" not in flask.request.json:
        raise util.APIError(400, message="Opponents array is required.")

    if not flask.request.json["opponents"]:
        raise util.APIError(400, message="Non-empty opponents array is required.")

    # Validate unique usernames
    opponents = [{
        "name": "my-bot",
        "bot_id": "self",
    }]
    usernames = set(["my-bot"])
    for opponent in flask.request.json["opponents"]:
        if not BOT_NAME_RE.match(opponent["name"]):
            raise util.APIError(
                400,
                message="Invalid bot name {}".format(opponent["name"]))
        if opponent["name"] in usernames:
            raise util.APIError(
                400,
                message="Duplicate bot name {}".format(opponent["name"]))

        opponents.append({
            "name": opponent["name"],
            "bot_id": opponent["bot_id"],
        })

    env_params = {}
    for key, value in flask.request.json.items():
        if key in ("width", "height", "s", "no-timeout", "turn-limit"):
            env_params[key] = value

    entity = ondemand.check_status(user_id)
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=15)
    if entity and entity["last_updated"] >= cutoff:
        raise util.APIError(
            400,
            message="You last created a game less than 15 seconds ago, please wait and try again.")

    # TODO: check that user has a bot in the editor bucket (tutorial
    # bucket?)
    ondemand.launch(user_id, opponents, env_params, {})
    return util.response_success()


@web_api.route("/ondemand/<int:intended_user>", methods=["PUT"])
@util.cross_origin(methods=["GET", "POST", "PUT"])
@web_util.requires_login(accept_key=False)
def continue_ondemand(intended_user, *, user_id):
    if user_id != intended_user:
        raise web_util.user_mismatch_error(
            message="Cannot continue ondemand game for another user.")

    num_turns = 1
    # Default to resuming from the most recent snapshot, if present.
    snapshot_index = -1

    if flask.request.json:
        if flask.request.json.get("turn-limit"):
            num_turns = flask.request.json["turn-limit"]
        if flask.request.json.get("snapshot-index"):
            snapshot_index = flask.request.json["snapshot-index"]

    ondemand.continue_game(user_id, num_turns, snapshot_index)

    return util.response_success()


@web_api.route("/ondemand/<int:intended_user>/replay", methods=["GET"])
@util.cross_origin(methods=["GET"])
@web_util.requires_login(accept_key=False)
def get_ondemand_replay(intended_user, *, user_id):
    if user_id != intended_user:
        raise web_util.user_mismatch_error(
            message="Cannot get replay for another user.")

    bucket = model.get_ondemand_replay_bucket()
    blob = gcloud_storage.Blob("ondemand_{}".format(user_id), bucket, chunk_size=262144)
    buffer = io.BytesIO()

    try:
        blob.download_to_file(buffer)
    except gcloud_exceptions.NotFound:
        raise util.APIError(404, message="Replay not found.")

    buffer.seek(0)
    response = web_util.no_cache(flask.make_response(flask.send_file(
        buffer,
        mimetype="application/x-halite-3-replay",
        as_attachment=True,
        attachment_filename="{}.hlt".format(user_id))))

    response.headers["Content-Length"] = str(buffer.getbuffer().nbytes)

    return response


@web_api.route("/ondemand/<int:intended_user>/error_log", methods=["GET"])
@util.cross_origin(methods=["GET"])
@web_util.requires_login(accept_key=False)
def get_ondemand_log(intended_user, *, user_id):
    if user_id != intended_user:
        raise web_util.user_mismatch_error(
            message="Cannot get error log for another user.")

    bucket = model.get_ondemand_replay_bucket()
    blob = gcloud_storage.Blob("ondemand_log_{}".format(user_id), bucket, chunk_size=262144)
    buffer = io.BytesIO()

    try:
        blob.download_to_file(buffer)
    except gcloud_exceptions.NotFound:
        raise util.APIError(404, message="Error log not found.")

    buffer.seek(0)
    response = web_util.no_cache(flask.make_response(flask.send_file(
        buffer,
        mimetype="text/plain",
        as_attachment=True,
        attachment_filename="{}.log".format(user_id))))

    response.headers["Content-Length"] = str(buffer.getbuffer().nbytes)

    return response


@web_api.route("/ondemand/<int:intended_user>/bot_log", methods=["GET"])
@util.cross_origin(methods=["GET"])
@web_util.requires_login(accept_key=False)
def get_ondemand_bot_log(intended_user, *, user_id):
    if user_id != intended_user:
        raise web_util.user_mismatch_error(
            message="Cannot get bot log for another user.")

    bucket = model.get_ondemand_replay_bucket()
    blob = gcloud_storage.Blob("ondemand_bot_log_{}".format(user_id), bucket, chunk_size=262144)
    buffer = io.BytesIO()

    try:
        blob.download_to_file(buffer)
    except gcloud_exceptions.NotFound:
        raise util.APIError(404, message="Error log not found.")

    buffer.seek(0)
    response = web_util.no_cache(flask.make_response(flask.send_file(
        buffer,
        mimetype="text/plain",
        as_attachment=True,
        attachment_filename="{}.log".format(user_id))))

    response.headers["Content-Length"] = str(buffer.getbuffer().nbytes)

    return response
