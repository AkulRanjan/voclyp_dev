import React, { useState } from 'react';
import { View, StyleSheet, SafeAreaView } from 'react-native';
import { Button, TextInput, Text } from 'react-native-paper';
import { useDispatch, useSelector } from 'react-redux';
import { loginStart, loginSuccess, loginFailure, User } from '../../store/auth.slice';
import { RootState } from '../../store';
import { getAPIClient } from '../../api/client';
import { BRAND } from '../../config';

export function LoginScreen({ navigation }: any) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const dispatch = useDispatch();
  const { loading, error } = useSelector((state: RootState) => state.auth);

  const handleLogin = async () => {
    if (!email || !password) {
      return;
    }
    dispatch(loginStart());
    try {
      const api = getAPIClient();
      const response = await api.login(email, password);
      api.setToken(response.token);
      let user = {
        email: response.user.email,
        name: response.user.name,
        role: response.user.role as User['role'],
        tenant_id: response.user.tenant,
      };
      try {
        const me = await api.getMe();
        user = { ...user, user_id: me.user_id, tenant_id: me.tenant || user.tenant_id };
      } catch {
        /* keep login payload */
      }
      dispatch(
        loginSuccess({
          token: response.token,
          user,
        })
      );
    } catch (err: any) {
      dispatch(loginFailure(err.message));
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        <Text style={styles.title}>VoClyp</Text>
        <Text style={styles.subtitle}>Sales Insights & Recommendations</Text>

        <TextInput
          label="Email"
          value={email}
          onChangeText={setEmail}
          mode="outlined"
          style={styles.input}
          keyboardType="email-address"
          editable={!loading}
        />

        <TextInput
          label="Password"
          value={password}
          onChangeText={setPassword}
          mode="outlined"
          secureTextEntry
          style={styles.input}
          editable={!loading}
        />

        {error && <Text style={styles.error}>{error}</Text>}

        <Button
          mode="contained"
          onPress={handleLogin}
          loading={loading}
          disabled={loading || !email || !password}
          style={styles.button}
        >
          Sign In
        </Button>

        <Button
          mode="text"
          onPress={() => navigation.navigate('Signup')}
          disabled={loading}
          style={styles.linkButton}
        >
          Don't have an account? Sign Up
        </Button>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: BRAND.background,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 20,
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#1f2430',
    textAlign: 'center',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#666',
    textAlign: 'center',
    marginBottom: 40,
  },
  input: {
    marginBottom: 16,
  },
  button: {
    marginTop: 20,
    paddingVertical: 6,
  },
  linkButton: {
    marginTop: 16,
  },
  error: {
    color: '#d32f2f',
    marginBottom: 12,
    textAlign: 'center',
  },
});
