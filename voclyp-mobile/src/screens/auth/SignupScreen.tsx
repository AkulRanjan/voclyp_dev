import React, { useState } from 'react';
import { View, StyleSheet, SafeAreaView } from 'react-native';
import { Button, TextInput, Text } from 'react-native-paper';
import { useDispatch, useSelector } from 'react-redux';
import { loginStart, loginSuccess, loginFailure } from '../../store/auth.slice';
import { RootState } from '../../store';
import { getAPIClient } from '../../api/client';

export function SignupScreen({ navigation }: any) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [org, setOrg] = useState('');
  const dispatch = useDispatch();
  const { loading, error } = useSelector((state: RootState) => state.auth);

  const handleSignup = async () => {
    if (!name || !email || !password || !org) {
      return;
    }
    dispatch(loginStart());
    try {
      const api = getAPIClient();
      const response = await api.signup(email, password, name, org);
      api.setToken(response.token);
      dispatch(
        loginSuccess({
          token: response.token,
          user: {
            email: response.user.email,
            name: response.user.name,
            role: response.user.role as any,
            tenant_id: response.user.tenant,
          },
        })
      );
    } catch (err: any) {
      dispatch(loginFailure(err.message));
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        <Text style={styles.title}>Create Account</Text>

        <TextInput
          label="Organization/Company Name"
          value={org}
          onChangeText={setOrg}
          mode="outlined"
          style={styles.input}
          editable={!loading}
        />

        <TextInput
          label="Your Name"
          value={name}
          onChangeText={setName}
          mode="outlined"
          style={styles.input}
          editable={!loading}
        />

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
          onPress={handleSignup}
          loading={loading}
          disabled={loading || !name || !email || !password || !org}
          style={styles.button}
        >
          Sign Up
        </Button>

        <Button
          mode="text"
          onPress={() => navigation.navigate('LoginStack')}
          disabled={loading}
          style={styles.linkButton}
        >
          Already have an account? Sign In
        </Button>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f7f8fa',
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 20,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#1f2430',
    textAlign: 'center',
    marginBottom: 30,
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
