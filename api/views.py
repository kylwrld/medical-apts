from django.shortcuts import render, get_object_or_404, HttpResponse
from .models import *
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenObtainSerializer
from rest_framework_simplejwt.tokens import Token, AccessToken, RefreshToken
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password
from rest_framework_simplejwt.authentication import JWTStatelessUserAuthentication

from .serializers import *

from time import perf_counter 


class MyRefreshToken(RefreshToken):
    @classmethod
    def for_user(cls, user):
        token = cls()
        token['name'] = user.paciente.nome
        token['social_name'] = user.paciente.nome_social
        token['cpf'] = user.cpf

        if api_settings.CHECK_REVOKE_TOKEN:
            token[api_settings.REVOKE_TOKEN_CLAIM] = get_md5_hash_password(
                user.password
            )

        return token

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    token_class = MyRefreshToken

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['name'] = user.paciente.nome
        token['social_name'] = user.paciente.nome_social
        token['cpf'] = user.cpf

        return token

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

class Login(APIView):
    # parameters:
    #               cpf, password

    def post(self, request, format=None):
        user = get_object_or_404(Cadastro, cpf=request.data["cpf"])

        correct_password = user.check_password(request.data["password"])
        if not correct_password:
            return Response({"detail":"Not found"}, status=status.HTTP_404_NOT_FOUND)
        

        s = perf_counter()
        tokens = MyRefreshToken().for_user(user)

        e = perf_counter()
        print("SECONDS: ", e-s)

        data = {
            "refresh": str(tokens),
            "access": str(tokens.access_token),
        }


        return Response({"detail":"approved", "token":data}, status=status.HTTP_201_CREATED)

from django.core.handlers.wsgi import WSGIRequest

class Signup(APIView):
    serializer_class = PacienteSerializer

    # parameters: 
    #               cpf, password, nome, nome_social, cns
    #               uf, cidade, bairro, complemento, cep
    
    def post(self, request: WSGIRequest, format=None):
        serializer = PacienteSerializer(data=request.data)

        if serializer.is_valid():
            paciente = serializer.save()


            Endereco.objects.create(uf=request.data["uf"], cidade=request.data["cidade"], bairro=request.data["bairro"], 
                                               complemento=request.data["complemento"], cep=request.data["cep"], paciente=paciente)


            cadastro = Cadastro.objects.create(cpf=paciente.cpf, paciente=paciente)
            cadastro.set_password(request.data["password"])
            cadastro.save()

            paciente_serializer = PacienteSerializerReadOnly(paciente)

            s = perf_counter()
            refresh = MyRefreshToken().for_user(cadastro)
            e = perf_counter()
            print("SECONDS: ", e-s)
            
            data = {
                "refresh":str(refresh),
                "access":str(refresh.access_token),
                "user": paciente_serializer.data,
            }
            
            return Response(data=data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors)

class Consulta(APIView):
    # parameters: 
    #               espcialidade, descricao
    #               preferencia, cpf, nome_fila

    def post(self, request: WSGIRequest, format=None):
        agendamento_serializer = AgendamentoSerializer(data=request.data)

        if agendamento_serializer.is_valid():
            paciente = get_object_or_404(Paciente, cpf=request.data["cpf"])

            if len(Agendamento.objects.filter(especialidade=request.data["especialidade"], paciente=paciente)) >= 1:
                return Response({"detail":"Consulta com médico já criada."}, status=status.HTTP_400_BAD_REQUEST)

            fila, is_created = Fila.objects.get_or_create(nome_fila=request.data["nome_fila"], 
                                                          especialidade=request.data["especialidade"])
            paciente.filas.add(fila)
            paciente.save()
            agendamento = agendamento_serializer.save(paciente=paciente)
            
            
            s = perf_counter()
            alocacao = Alocacao.objects.filter(paciente=paciente)
            alocacao = alocacao[len(alocacao)-1]
            alocacao.save(agendamento=agendamento)
            e = perf_counter()
            print("SECONDS: ", e-s)

            return Response(agendamento_serializer.data)
            
        return Response(agendamento_serializer.errors)
    
class ConsultaUser(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request: WSGIRequest, format=None):
        paciente = Paciente.objects.get(cpf=request.data["cpf"])

        alocacao = Alocacao.objects.filter(paciente=paciente)
        alocacao = alocacao[len(alocacao)-1]

        alocacao.save()

        return Response({"data":"ok!"})
    
    def delete(self, request, format=None):
        paciente = Paciente.objects.get(cpf=request.user.cpf)
        agendamento = get_object_or_404(Agendamento, paciente=paciente, especialidade=request.data["especialidade"])
        agendamento.delete()
        fila = Fila.objects.get(nome_fila=request.data["nome_fila"], especialidade=request.data["especialidade"])
        paciente.filas.remove(fila)

        return Response(data={"detailt":"Item successfully deleted"}, status=status.HTTP_200_OK)
    
    # parameters:
    #               nova_especialidade + AgendamentoModelFields
    def put(self, request, format=None):
        agendamento = get_object_or_404(Agendamento, paciente=request.user.paciente, especialidade=request.data["especialidade"])

        if "nova_especialidade" in request.data:
            request.data["especialidade"] = request.data["nova_especialidade"]

        agendamento_serializer = AgendamentoSerializer(agendamento, data=request.data)

        if agendamento_serializer.is_valid():
            agendamento_serializer.save()
            return Response(data=agendamento_serializer.data, status=status.HTTP_201_CREATED)
        return Response(data=agendamento_serializer.errors, status=status.HTTP_400_BAD_REQUEST)



def teste(request):
    cpf = "123.123.123-57"
    password = "1234"
    nome = "Daniel"
    nome_social = "teste"
    cns = 12345 
    uf = "pe" 
    cidade = "recife"
    bairro = "encruzilhada" 
    complemento = "apt x"
    cep = "08326498"

    paciente = Paciente.objects.get(cpf=cpf)
    alocacao = Alocacao.objects.filter(paciente=paciente)

    print(alocacao)

    return HttpResponse("Oi")