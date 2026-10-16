import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import type { paths } from '../api/api-types';

// Le type est dérivé du contrat OpenAPI généré.
// Aucun modèle Pokémon n'est redéfini manuellement.
export type PokemonList =
  paths['/pokemon']['get']['responses'][200]['content']['application/json'];

export type Pokemon = PokemonList extends Array<infer T> ? T : never;

@Injectable({
  providedIn: 'root',
})
export class PokemonApiService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = '/api';

  /**
   * Récupère une liste paginée de Pokémon.
   */
  getPokemon(limit: number = 20, offset: number = 0): Observable<PokemonList> {
    return this.http.get<PokemonList>(`${this.apiUrl}/pokemon`, {
      params: { limit, offset },
    });
  }
}
