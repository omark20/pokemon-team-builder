// One tab per team, in the order the teams were made, then "New team". All
// teams are already loaded, so selecting a tab needs no request. A dot marks a
// team holding a Pokémon that an undismissed change alert names.
import type { Team } from "../types";

interface TabsProps {
  teams: Team[];
  activeId: number | null;
  creating: boolean; // a team is being made; "New team" waits
  alertTeamIds: Set<number>; // teams that get a dot
  onSelect: (id: number) => void;
  onNew: () => void;
}

export function TeamTabs({ teams, activeId, creating, alertTeamIds, onSelect, onNew }: TabsProps) {
  return (
    <nav className="tabs" aria-label="Your teams">
      {teams.map((team) => (
        <button
          key={team.id}
          type="button"
          className="tab"
          aria-pressed={team.id === activeId}
          onClick={() => onSelect(team.id)}
        >
          {team.name}
          {alertTeamIds.has(team.id) && <span className="tab-dot" role="img" aria-label="has a change alert" />}
        </button>
      ))}
      <button type="button" className="tab tab-new" disabled={creating} onClick={onNew}>
        + New team
      </button>
    </nav>
  );
}
