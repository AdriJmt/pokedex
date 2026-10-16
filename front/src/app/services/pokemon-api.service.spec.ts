import { TestBed } from '@angular/core/testing';

import { PokemonApiService } from './pokemon-api.service';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';

describe('PokemonApiService', () => {
  let service: PokemonApiService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        PokemonApiService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });

    service = TestBed.inject(PokemonApiService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
