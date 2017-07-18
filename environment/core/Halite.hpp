#ifndef HALITE_H
#define HALITE_H


#ifdef _WIN32
#define NOMINMAX
#undef min
#undef max
#define _USE_MATH_DEFINES
#endif

#include <cmath>
#include <fstream>
#include <string>
#include <map>
#include <memory>
#include <set>
#include <algorithm>
#include <iostream>
#include <thread>
#include <future>

#include "hlt.hpp"
#include "json.hpp"

#include "./mapgen/Generator.h"
#include "../networking/Networking.hpp"

extern bool quiet_output;

struct PlayerStatistics {
    int tag;
    int rank;
    int last_frame_alive;
    int init_response_time;
    double average_frame_response_time;
    int total_ship_count;
    int damage_dealt;
};

struct GameStatistics {
    std::vector<PlayerStatistics> player_statistics;
    std::string output_filename;
    std::set<unsigned short> timeout_tags;
    std::vector<std::string> timeout_log_filenames;
};

auto to_json(nlohmann::json& json, const GameStatistics& stats) -> void;

/**
 * An event that happens during game simulation. Recorded for the replay, so
 * that visualizers have more information to use.
 */
struct Event {
    virtual auto serialize() -> nlohmann::json = 0;

    Event() {};
};

struct DestroyedEvent : Event {
    hlt::EntityId id;
    hlt::Location location;
    double radius;

    DestroyedEvent(hlt::EntityId id_, hlt::Location location_, double radius_)
        : id(id_), location(location_), radius(radius_) {};

    auto serialize() -> nlohmann::json {
        return nlohmann::json{
            { "event", "destroyed" },
            { "entity", id },
            { "x", location.pos_x },
            { "y", location.pos_y },
            { "radius", radius },
        };
    }
};

struct AttackEvent : Event {
    hlt::EntityId id;
    hlt::Location location;

    std::vector<hlt::EntityId> targets;
    std::vector<hlt::Location> target_locations;

    AttackEvent(hlt::EntityId id_, hlt::Location location_,
                std::vector<hlt::EntityId> targets_,
                std::vector<hlt::Location> target_locations_) :
        id(id_), location(location_), targets(targets_),
        target_locations(target_locations_) {};

    auto serialize() -> nlohmann::json {
        std::vector<nlohmann::json> target_locations;
        target_locations.reserve(targets.size());
        for (auto& location : targets) {
            target_locations.push_back(location);
        }
        return nlohmann::json{
            { "event", "attack" },
            { "entity", id },
            { "x", location.pos_x },
            { "y", location.pos_y },
            { "targets", targets },
            { "target_locations", target_locations },
        };
    }
};

struct SpawnEvent : Event {
    hlt::EntityId id;
    hlt::Location location;
    hlt::Location planet_location;

    SpawnEvent(hlt::EntityId id_, hlt::Location location_,
               hlt::Location planet_location_)
        : id(id_), location(location_), planet_location(planet_location_) {}

    auto serialize() -> nlohmann::json {
        return nlohmann::json{
            { "event", "spawned" },
            { "entity", id },
            { "x", location.pos_x },
            { "y", location.pos_y },
            { "planet_x", planet_location.pos_x },
            { "planet_y", planet_location.pos_y },
        };
    }
};

typedef std::array<hlt::entity_map<double>, hlt::MAX_PLAYERS> DamageMap;

class Halite {
private:
    //Networking
    Networking networking;

    //Game state
    unsigned short turn_number;
    unsigned short number_of_players;
    bool ignore_timeout;
    hlt::Map game_map;
    std::vector<std::string> player_names;
    hlt::MoveQueue player_moves;

    unsigned int seed;
    std::string map_generator;

    //Statistics
    std::vector<unsigned short> alive_frame_count;
    std::vector<unsigned int> init_response_times;
    std::vector<unsigned int> last_ship_count;
    std::vector<unsigned int> last_ship_health_total;
    std::vector<unsigned int> total_ship_count;
    std::vector<unsigned int> kill_count;
    std::vector<unsigned int> damage_dealt;
    std::vector<unsigned int> total_frame_response_times;
    std::set<unsigned short> timeout_tags;

    //Full game
    //! A record of the game state at every turn, used for replays.
    std::vector<hlt::Map> full_frames;
    std::vector<std::vector<std::unique_ptr<Event>>> full_frame_events;
    std::vector<hlt::MoveQueue> full_player_moves;
    std::vector<mapgen::PointOfInterest> points_of_interest;

    //! Grab the next set of moves from the bots
    auto retrieve_moves(std::vector<bool> alive) -> void;

    std::vector<bool> process_next_frame(std::vector<bool> alive);
    auto output_header(nlohmann::json& replay) -> void;
    auto output(std::string filename) -> void;
    void kill_player(hlt::PlayerId player);

    //! Compute the damage between two colliding ships
    auto compute_damage(hlt::EntityId self_id, hlt::EntityId other_id)
        -> std::pair<unsigned short, unsigned short>;

    // Subparts of game loop
    auto process_damage(DamageMap& ship_damage) -> void;
    auto process_docking() -> void;
    auto process_production() -> void;
    auto process_drag() -> void;
    auto process_cooldowns() -> void;
    auto process_moves(std::vector<bool>& alive, int move_no) -> void;
    auto process_events() -> void;
    auto process_movement() -> void;
    auto find_living_players() -> std::vector<bool>;

    //! Helper to damage an entity and kill it if necessary
    auto damage_entity(hlt::EntityId id, unsigned short damage) -> void;
    //! Helper to kill an entity and clean up any dependents (planet
    //! explosions, docked ships, etc.)
    auto kill_entity(hlt::EntityId id) -> void;

    //! Comparison function to rank two players, based on the number of ships and their total health.
    auto compare_rankings(const hlt::PlayerId& player1,
                          const hlt::PlayerId& player2) const -> bool;
public:
    Halite(unsigned short width_,
           unsigned short height_,
           unsigned int seed_,
           unsigned short n_players_for_map_creation,
           Networking networking_,
           bool should_ignore_timeout);

    GameStatistics run_game(std::vector<std::string>* names_,
                            unsigned int id,
                            bool enable_replay,
                            std::string replay_directory);
    std::string get_name(hlt::PlayerId player_tag);

    ~Halite();
};

#endif
