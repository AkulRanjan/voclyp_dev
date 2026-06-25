import axios, { AxiosInstance } from 'axios';
import { API_BASE } from '../config';
import { audioUploadMime, audioUploadName } from '../audio/recordingOptions';

export interface Insight {
  schema_version: string;
  conversation_id: string;
  store_id?: string;
  languages: { detected: string[]; normalized_to: string };
  signals: any[];
  summary: { text: string; fields: Record<string, string> };
  privacy: { consent_captured: boolean; pii_redactions: Record<string, number> };
  audit: Record<string, any>;
  created_at: string;
}

export interface LoginResponse {
  token: string;
  user: {
    email: string;
    name: string;
    role: string;
    tenant: string;
  };
}

export interface Store {
  store_id: string;
  name: string;
  area_id: string;
  manager_id: string;
  latitude?: number;
  longitude?: number;
  address?: string;
  status: string;
}

class APIClient {
  private client: AxiosInstance;
  private token: string | null = null;
  private baseURL: string;

  constructor(baseURL: string = 'http://localhost:8000') {
    this.baseURL = baseURL;
    this.client = axios.create({
      baseURL,
      timeout: 30000,
    });

    // Add auth header interceptor
    this.client.interceptors.request.use(
      (config) => {
        if (this.token) {
          config.headers.Authorization = `Bearer ${this.token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Handle 401 responses
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          this.token = null;
          this.onUnauthorized?.();
          const friendly = new Error('Session expired — please sign in again.');
          (friendly as any).status = 401;
          return Promise.reject(friendly);
        }
        return Promise.reject(error);
      }
    );
  }

  private onUnauthorized: (() => void) | null = null;

  setOnUnauthorized(handler: (() => void) | null) {
    this.onUnauthorized = handler;
  }

  clearToken() {
    this.token = null;
  }

  setToken(token: string) {
    this.token = token;
  }

  async signup(email: string, password: string, name: string, org: string) {
    try {
      const response = await this.client.post<LoginResponse>('/auth/signup', {
        email,
        password,
        name,
        org,
      });
      this.token = response.data.token;
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Signup failed');
    }
  }

  async login(email: string, password: string) {
    try {
      const response = await this.client.post<LoginResponse>('/auth/login', {
        email,
        password,
      });
      this.token = response.data.token;
      return response.data;
    } catch (error: any) {
      if (!error.response) {
        throw new Error(
          `Cannot reach server at ${this.baseURL}. ` +
            'Use the same Wi‑Fi as your PC, restart the backend, and check EXPO_PUBLIC_API_URL in voclyp-mobile/.env',
        );
      }
      throw new Error(error.response?.data?.detail || 'Login failed');
    }
  }

  async getMe() {
    try {
      const response = await this.client.get('/auth/me');
      return response.data.user as {
        email: string;
        name: string;
        role: string;
        tenant: string;
        user_id?: string;
      };
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Failed to get user info');
    }
  }

  async logout() {
    try {
      await this.client.post('/auth/logout', {});
      this.token = null;
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Logout failed');
    }
  }

  async uploadConversation(
    audio: Blob,
    metadata: {
      agent_id: string;
      store_id: string;
      customer_name: string;
      customer_phone: string;
      consent_captured: boolean;
    }
  ) {
    try {
      const formData = new FormData();
      formData.append('audio', audio, 'recording.wav');
      formData.append('agent_id', metadata.agent_id);
      formData.append('store_id', metadata.store_id);
      formData.append('customer_name', metadata.customer_name);
      formData.append('customer_phone', metadata.customer_phone);
      formData.append('consent_captured', metadata.consent_captured ? 'true' : 'false');
      formData.append('client_ref', `mobile-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);

      const response = await this.client.post('/v1/conversations', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Failed to upload conversation');
    }
  }

  async getInsight(conversation_id: string) {
    try {
      const response = await this.client.get<Insight>(`/v1/insights/${conversation_id}`);
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return null; // Still processing
      }
      throw new Error(error.response?.data?.detail || 'Failed to get insight');
    }
  }

  async getConversationStatus(conversation_id: string) {
    try {
      const response = await this.client.get<{ status: string; error?: string }>(
        `/v1/conversations/${conversation_id}/status`,
      );
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Failed to get processing status');
    }
  }

  async listInsights() {
    try {
      const response = await this.client.get('/v1/insights');
      return response.data.insights;
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Failed to list insights');
    }
  }

  async listStores(area_id?: string) {
    try {
      const params = area_id ? { area_id } : {};
      const response = await this.client.get('/v1/stores', { params });
      return response.data.stores;
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Failed to list stores');
    }
  }

  async getStore(store_id: string): Promise<Store> {
    try {
      const response = await this.client.get(`/v1/stores/${store_id}`);
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Failed to get store');
    }
  }

  async getAreas() {
    try {
      const response = await this.client.get('/v1/areas');
      return response.data.areas;
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Failed to list areas');
    }
  }

  async sendWhatsAppRecommendation(
    conversation_id: string,
    customer_phone: string,
    products: Array<{ name: string; sku: string; price: number }>,
    rep_name: string,
    message_body?: string
  ) {
    try {
      const response = await this.client.post('/v1/recommendations/whatsapp-send', {
        conversation_id,
        customer_phone,
        products,
        rep_name,
        message_body,
      });
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Failed to send recommendation');
    }
  }

  async getRecommendationStatus(message_id: string) {
    try {
      const response = await this.client.get(`/v1/recommendations/${message_id}`);
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Failed to get recommendation status');
    }
  }

  async listRecommendations(customer_phone: string) {
    try {
      const response = await this.client.get('/v1/recommendations', {
        params: { customer_phone },
      });
      return response.data.recommendations;
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Failed to list recommendations');
    }
  }

  async startSession(store_id: string, agent_id?: string) {
    const response = await this.client.post('/v1/sessions', { store_id, agent_id });
    return response.data as { session_id: string; ws_url: string; status: string };
  }

  async patchSession(
    session_id: string,
    fields: { customer_name?: string; customer_phone?: string },
  ) {
    const response = await this.client.patch(`/v1/sessions/${session_id}`, fields);
    return response.data;
  }

  async consentSession(session_id: string) {
    const response = await this.client.post(`/v1/sessions/${session_id}/consent`);
    return response.data;
  }

  async completeSession(session_id: string, audioUri?: string | null) {
    if (audioUri) {
      const formData = new FormData();
      const name = audioUploadName(audioUri);
      formData.append('audio', {
        uri: audioUri,
        name,
        type: audioUploadMime(audioUri),
      } as any);
      const response = await this.client.post(
        `/v1/sessions/${session_id}/complete`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 300000,
        },
      );
      return response.data as { conversation_id: string; status: string };
    }
    const response = await this.client.post(`/v1/sessions/${session_id}/complete`);
    return response.data as { conversation_id: string; status: string };
  }

  async getCatalog() {
    const response = await this.client.get('/v1/catalog');
    return response.data;
  }

  async getInsightRecommendations(conversation_id: string) {
    const response = await this.client.get(
      `/v1/insights/${conversation_id}/recommendations`,
    );
    return response.data.products as Array<Record<string, unknown>>;
  }

  async getVoiceprintStatus() {
    const response = await this.client.get('/v1/voiceprints/me');
    return response.data as {
      enrolled: boolean;
      samples: number;
      model?: string;
      updated_at?: string;
    };
  }

  async enrollVoiceprint(audioUri: string) {
    const formData = new FormData();
    const name = audioUploadName(audioUri);
    formData.append('audio', {
      uri: audioUri,
      name,
      type: audioUploadMime(audioUri),
    } as any);
    const response = await this.client.post('/v1/voiceprints/enroll', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data as {
      enrolled: boolean;
      model: string;
      samples: number;
      dims: number;
    };
  }
}

// Singleton instance
let apiClientInstance: APIClient | null = null;

export function initAPIClient(baseURL: string) {
  if (!apiClientInstance) {
    apiClientInstance = new APIClient(baseURL);
  }
  return apiClientInstance;
}

export function getAPIClient(): APIClient {
  if (!apiClientInstance) {
    apiClientInstance = new APIClient(API_BASE);
  }
  return apiClientInstance;
}

export default APIClient;
